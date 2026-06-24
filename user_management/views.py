from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status  
from django.shortcuts import get_object_or_404
from rest_framework.authtoken.models import Token
from decimal import Decimal

from restaurant.models import Table, Restaurant, Payment
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from django.db.models import Max, Sum
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
from .serializers import CustomerProfileSerializer, BookingSerializer, MenuBookingSerializer, BillingSerializer, BillingSerializer, SeatBookingSerializer, ReviewSerializer, SpecialRequestForSeatSerializer, SpecialRequestMessageSerializer, NotificationSerializer, AddressSerializer
from restaurant.serializers import TableSerializer, RestaurantSerializer
from .models import CustomerProfile, Booking, MenuBooking, Billing, SeatBooking, Review, SpecialRequestForSeat, SpecialRequestMessage, Notification, Address

import re
import os
import requests as req
from urllib.parse import urlencode
from .models import OTP
from .utils import send_otp_via_messagecentral, _get_auth_token

import razorpay
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import hmac
import hashlib
import json

# ── Constants ──────────────────────────────────────────────────
OTP_TTL_SECONDS = 300
MAX_OTP_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 30


class SendOTPView(APIView):
    def post(self, request):
        phone = request.data.get('phone')

        if not phone:
            return Response(
                {"error": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not re.match(r'^[6-9]\d{9}$', str(phone)):
            return Response(
                {"error": "Enter a valid 10-digit Indian mobile number."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Resend cooldown
        last_otp = OTP.objects.filter(
            phone=phone,
            is_used=False,
            is_expired=False
        ).order_by('-created_at').first()

        if last_otp:
            seconds_passed = (timezone.now() - last_otp.created_at).total_seconds()
            if seconds_passed < RESEND_COOLDOWN_SECONDS:
                retry_after = int(RESEND_COOLDOWN_SECONDS - seconds_passed)
                return Response(
                    {
                        "error": "Please wait before requesting another OTP.",
                        "retry_after_seconds": retry_after
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            # Expire old OTP
            last_otp.is_expired = True
            last_otp.save()

        # Send OTP
        sms_text = "Your Social Monkey verification code is <<< OTP >>>. Valid for 5 minutes. Do not share."
        ok, provider_resp = send_otp_via_messagecentral(phone, sms_text)
        if not ok:
            return Response(
                {"error": "Failed to send OTP. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Save OTP record
        otp_obj = OTP.objects.create(phone=phone)
        data = provider_resp.get("data") if isinstance(provider_resp, dict) else None
        if data:
            otp_obj.provider_verification_id = data.get("verificationId")
            otp_obj.provider_transaction_id = data.get("transactionId")
            otp_obj.save()

        return Response(
            {"message": "OTP sent successfully.", "expires_in": "5 minutes"},
            status=status.HTTP_200_OK
        )


class VerifyOTPView(APIView):
    def post(self, request):
        phone = request.data.get('phone')
        otp_code = request.data.get('otp')

        if not phone or not otp_code:
            return Response(
                {"error": "Phone and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )


        # Get latest valid OTP
        try:
            otp = OTP.objects.filter(
                phone=phone,
                is_used=False,
                is_expired=False
            ).latest('created_at')
        except OTP.DoesNotExist:
            return Response(
                {"error": "No OTP found. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check expiry
        expiry_time = otp.created_at + timedelta(seconds=OTP_TTL_SECONDS)
        if timezone.now() > expiry_time:
            otp.is_expired = True
            otp.save()
            return Response(
                {"error": "OTP has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check max attempts
        if otp.attempts >= MAX_OTP_ATTEMPTS:
            otp.is_expired = True
            otp.save()
            return Response(
                {"error": "Too many attempts. Please request a new OTP."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Increment attempt BEFORE calling provider
        otp.attempts += 1
        otp.save()

        # Verify with MessageCentral
        verification_id = otp.provider_verification_id
        if not verification_id:
            return Response(
                {"error": "Verification ID missing. Please request a new OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        country = os.environ.get("MESSAGECENTRAL_COUNTRY_CODE", "91")
        customer_id = os.environ.get("MESSAGECENTRAL_CUSTOMER_ID")
        base = os.environ.get("MESSAGECENTRAL_BASE", "https://cpaas.messagecentral.com")

        params = {
            "countryCode": country,
            "mobileNumber": phone,
            "verificationId": verification_id,
            "customerId": customer_id,
            "code": otp_code
        }
        validate_url = f"{base}/verification/v3/validateOtp?{urlencode(params)}"

        ok, token_or_err = _get_auth_token(country=country)
        if not ok:
            return Response(
                {"error": "Auth error. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        headers = {"authToken": token_or_err, "Accept": "application/json"}

        try:
            resp = req.get(validate_url, headers=headers, timeout=10)
        except Exception:
            return Response(
                {"error": "Network error. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            j = resp.json()
        except ValueError:
            j = {}

        # OTP wrong
        if not (resp.status_code == 200 and j.get("message") == "SUCCESS"):
           
            attempts_left = MAX_OTP_ATTEMPTS - otp.attempts
            return Response(
                {
                    "error": "Invalid OTP. Please try again.",
                    "attempts_remaining": max(attempts_left, 0)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # OTP correct
        otp.is_used = True
        otp.save()

        # Existing user
        existing_user = User.objects.filter(username=phone).first()
        if existing_user:
            token, _ = Token.objects.get_or_create(user=existing_user)
            try:
                profile = existing_user.customer_profile
                return Response(
                    {
                        "message": "Login successful.",
                        "is_new_user": False,
                        "token": token.key,
                        "profile": {
                            "id": profile.id,
                            "full_name": profile.full_name,
                            "phone": existing_user.username,
                            "gender": profile.gender,
                            "is_verified": profile.is_verified,
                        }
                    },
                    status=status.HTTP_200_OK
                )
            except CustomerProfile.DoesNotExist:
                pass

        # New user — create User + CustomerProfile
        new_user = User.objects.create(username=phone)
        profile = CustomerProfile.objects.create(
            user=new_user,
            full_name="",
            is_verified=True
        )
        token, _ = Token.objects.get_or_create(user=new_user)
        return Response(
            {
                "message": "OTP verified. Please complete your profile.",
                "is_new_user": True,
                "token": token.key,
                "profile": {
                    "id": profile.id,
                    "phone": phone,
                    "is_verified": True,
                }
            },
            status=status.HTTP_201_CREATED
        )

class CustomerProfileView(APIView):
    def post(self, request):
        serializer = CustomerProfileSerializer(data=request.data)
        if serializer.is_valid():
            profile = serializer.save()
            token, _ = Token.objects.get_or_create(user=profile.user)
            return Response({
                "message": "Signup successful",
                "token": token.key,
                "profile": CustomerProfileSerializer(profile).data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        users = CustomerProfile.objects.all()
        data = []
        for user in users:
            token, _ = Token.objects.get_or_create(user=user.user)
            serialized_profile = CustomerProfileSerializer(user).data
            serialized_profile["token"] = token.key
            data.append(serialized_profile)

        return Response(data, status=status.HTTP_200_OK)


class EditProfile(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Customer profile ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        profile = get_object_or_404(CustomerProfile, pk=pk, user=request.user)

        phone_number = request.data.get('phone_number')
        phone_changed = phone_number and phone_number != profile.user.username

        if phone_changed:
            profile.user.username = phone_number
            profile.user.save()

        serializer = CustomerProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            updated_profile = serializer.save()

            # ✅ Reset verification status if phone number changed
            if phone_changed:
                updated_profile.is_verified = False
                updated_profile.save()

            return Response({
                "message": "Customer profile updated successfully.",
                "profile": CustomerProfileSerializer(updated_profile).data
            }, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Customer profile ID (pk) is required."}, status=status.HTTP_400_BAD_REQUEST)
        profile = get_object_or_404(CustomerProfile, pk=pk, user=request.user)
        profile.profile_picture.delete(save=False)
        profile.profile_picture = None
        profile.save()
        return Response({"message": "Profile picture removed."}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RestaurantListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurants = Restaurant.objects.all()
        serializer = RestaurantSerializer(restaurants, many=True)
        return Response(serializer.data)


class SeatBookingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        bookings = SeatBooking.objects.filter(user=profile).order_by('-created_at')
        serializer = SeatBookingSerializer(bookings, many=True)
        return Response(serializer.data)

    def post(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SeatBookingSerializer(data=request.data)
        if serializer.is_valid():
            validated_data = serializer.validated_data

            seat_slot = validated_data['seat_slot']
            restaurant = validated_data['restaurant']
            offer = validated_data.get('offer')
            number_of_guests = validated_data['number_of_guests']

            now = timezone.now()
            confirmed = SeatBooking.objects.filter(
                seat_slot=seat_slot, payment_status='success'
            ).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            locked = SeatBooking.objects.filter(
                seat_slot=seat_slot, locked=True, lock_expiry__gt=now
            ).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            total_taken = confirmed + locked

            available = seat_slot.available_seats - total_taken  

            if available < number_of_guests:
                return Response({
                    "error": "Not enough seats available.",
                    "available_seats": max(0, available)
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                advance_per_guest = restaurant.payment.min_advance_amount
            except Payment.DoesNotExist:
                return Response({
                    "error": "Restaurant has no payment settings configured."
                }, status=status.HTTP_400_BAD_REQUEST)

            total_payment = advance_per_guest * number_of_guests
            if offer and offer.is_active:
                total_payment -= total_payment * (offer.discount_percentage / Decimal(100))

            booking = SeatBooking.objects.create(
                user=profile,
                restaurant=restaurant,
                seat_slot=seat_slot,
                offer=offer,
                number_of_guests=number_of_guests,
                total_advance_payment=total_payment,
                locked=True,
                lock_expiry=now + timezone.timedelta(minutes=3),
                payment_status='pending'
            )

            return Response({
                "message": "Seat locked successfully. Proceed to payment.",
                "booking": SeatBookingSerializer(booking).data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request, pk):
        if not pk:
            return Response({"error": "Booking ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        booking = get_object_or_404(SeatBooking, id=pk, user=profile)

        # Restore seats
        seat_slot = booking.seat_slot
        seat_slot.available_seats += booking.number_of_guests
        seat_slot.save()

        booking.delete()
        return Response({"message": "Booking cancelled successfully."}, status=status.HTTP_204_NO_CONTENT)


class ConfirmPaymentView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        booking_id = request.query_params.get("booking_id")
        now = timezone.now()

        if booking_id:
            try:
                booking = SeatBooking.objects.get(id=booking_id, user=request.user.customer_profile)
            except SeatBooking.DoesNotExist:
                return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

            confirmed = SeatBooking.objects.filter(
                seat_slot=booking.seat_slot,
                payment_status='success'
            ).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            locked = SeatBooking.objects.filter(
                seat_slot=booking.seat_slot,
                locked=True,
                lock_expiry__gt=now
            ).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            total_taken = confirmed + locked
            available = booking.seat_slot.available_seats - total_taken

            return Response({
                "booking_id": booking.id,
                "payment_status": booking.payment_status,
                "locked": booking.locked,
                "lock_expiry": booking.lock_expiry,
                "number_of_guests": booking.number_of_guests,
                "available_seats_for_this_booking": available,
                "seats_required": booking.number_of_guests,
                "can_confirm_now": available >= booking.number_of_guests,
            })

        else:
            bookings = SeatBooking.objects.filter(user=request.user.customer_profile).order_by('-created_at')
            data = [
                {
                    "booking_id": b.id,
                    "seat_slot": b.seat_slot.id,
                    "number_of_guests": b.number_of_guests,
                    "payment_status": b.payment_status,
                    "locked": b.locked,
                    "lock_expiry": b.lock_expiry,
                    "created_at": b.created_at,
                }
                for b in bookings
            ]

            return Response({"bookings": data})
    def post(self, request):
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')
        booking_id = request.data.get('booking_id')

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, booking_id]):
            return Response(
                {"error": "razorpay_order_id, razorpay_payment_id, razorpay_signature and booking_id are all required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify Razorpay actually signed this payment — replaces the old trust-based flag
        generated_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, razorpay_signature):
            return Response({"error": "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                booking = SeatBooking.objects.select_for_update().get(id=booking_id, user=request.user.customer_profile)
            except SeatBooking.DoesNotExist:
                return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

            if booking.payment_status == 'success':
                return Response({"status": "Booking confirmed!"})  # idempotent

            now = timezone.now()
            if booking.is_lock_expired():
                booking.release_lock()
                return Response({"error": "Booking expired."}, status=status.HTTP_400_BAD_REQUEST)

            confirmed = SeatBooking.objects.filter(
                seat_slot=booking.seat_slot, payment_status='success'
            ).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            locked = SeatBooking.objects.filter(
                seat_slot=booking.seat_slot, locked=True, lock_expiry__gt=now
            ).exclude(id=booking.id).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            available = booking.seat_slot.available_seats - (confirmed + locked)

            if available >= booking.number_of_guests:
                booking.payment_status = 'success'
                booking.locked = False
                booking.lock_expiry = None
                booking.save()
                return Response({"status": "Booking confirmed!"})
            else:
                booking.release_lock()
                return Response({"error": "Seats not available anymore."}, status=status.HTTP_400_BAD_REQUEST)

class SpecialRequestForSeatView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


    def post(self, request):
        booking_id = request.data.get('booking')  # This should be the SeatBooking ID
        message = request.data.get('message')
        print("data:", request.data)

        if not booking_id or not message:
            return Response({"error": "Booking ID and message are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Fetch the SeatBooking using booking ID and user
            booking = SeatBooking.objects.get(id=booking_id, user=request.user.customer_profile)

            # Get or create special request associated with SeatBooking
            special_request, created = SpecialRequestForSeat.objects.get_or_create(
                booking=booking,
                defaults={'message': message}
            )

            if not created:
                special_request.message = message
                special_request.save()

            return Response({
                "message": "Special request saved successfully.",
                "data": SpecialRequestForSeatSerializer(special_request).data
            }, status=status.HTTP_201_CREATED)

        except SeatBooking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        # Filter special requests based on SeatBooking and user
        special_requests = SpecialRequestForSeat.objects.filter(booking__user=profile)
        serializer = SpecialRequestForSeatSerializer(special_requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MenuBookingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)
        if not pk:
            return Response({"error": "Booking ID or Table ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        menu_bookings = MenuBooking.objects.filter(booking_id=pk)
        if not menu_bookings.exists():
            menu_bookings = MenuBooking.objects.filter(table_id=pk)

        if not menu_bookings.exists():
            return Response({"error": "No menu bookings found for this Booking or Table."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MenuBookingSerializer(menu_bookings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = MenuBookingSerializer(data=request.data)
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)
        
        if serializer.is_valid():
            booking = serializer.validated_data.get("booking")
            table = serializer.validated_data.get("table")

            if not booking and not table:
                return Response({"error": "Either Booking or Table must be provided."}, status=status.HTTP_400_BAD_REQUEST)
            if table.booking_status == True:
                return Response ({"error": "The Table already booked"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                menu_booking = serializer.save()
                if table:
                    table.booking_status = True
                    table.save()

            return Response({
                "message": "Menu item added successfully.",
                "user": profile.user.username,
                "data": MenuBookingSerializer(menu_booking).data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SpecialRequestMessageView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get("booking")
        message_text = request.data.get("message")

        if not booking_id or not message_text:
            return Response({"error": "Booking ID and message are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = MenuBooking.objects.get(id=booking_id)
        except MenuBooking.DoesNotExist:
            return Response({"error": "MenuBooking not found."}, status=status.HTTP_404_NOT_FOUND)

        if booking.booking.user.user != request.user:
            return Response({"error": "Unauthorized access to this booking."}, status=status.HTTP_403_FORBIDDEN)

        if hasattr(booking, 'special_request_message'):
            return Response({"error": "Special request already sent for this booking."}, status=status.HTTP_400_BAD_REQUEST)

        special_request = SpecialRequestMessage.objects.create(
            booking=booking,
            message=message_text
        )

        serializer = SpecialRequestMessageSerializer(special_request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get(self, request):
        from restaurant.models import Restaurant
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found."}, status=status.HTTP_404_NOT_FOUND)

        messages = SpecialRequestMessage.objects.filter(
            booking__table__restaurant=restaurant
        ).order_by('-created_at')

        serializer = SpecialRequestMessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BillingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if not pk:
            return Response({"error": "Booking ID or Table ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            billing = Billing.objects.get(booking_id=pk)
        except Billing.DoesNotExist:
            try:
                billing = Billing.objects.get(table_id=pk)
            except Billing.DoesNotExist:
                return Response({"error": "Billing not found for this booking."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BillingSerializer(billing)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)
        
        booking_id = request.data.get('booking')
        table_id = request.data.get('table')
        booking = None
        table = None
        if not booking_id and not table_id:
            return Response({"error": "Booking ID or Table ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if booking_id:
                booking = SeatBooking.objects.get(id=booking_id, user=request.user.customer_profile)
            if table_id:
                table = Table.objects.get(id=table_id)
            billing = None
            if booking:
                billing = Billing.objects.filter(booking=booking).first()
            if not billing and table:
                billing = Billing.objects.filter(table=table).first()
            if billing:
                if booking and not billing.booking:
                    billing.booking = booking
                if table and not billing.table:
                    billing.table = table
                billing.save()
            else:
                billing = Billing.objects.create(
                    booking=booking,
                    table=table
                )


            serializer = BillingSerializer(billing)
            return Response({
                "message": "Billing generated successfully.",
                "user": profile.user.username,
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)

        except SeatBooking.DoesNotExist:
            return Response({"error": "Booking not found or unauthorized."}, status=status.HTTP_404_NOT_FOUND)

        except Table.DoesNotExist:
            return Response({"error": "Table not found."}, status=status.HTTP_404_NOT_FOUND)



class CompleteOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    def post(self, request):
        booking_id = request.data.get("booking")
        table_id = request.data.get("table")

        if not booking_id and not table_id:
            return Response({"error": "Booking ID ot Table ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        billing = None

        try:
            if booking_id:
                booking = SeatBooking.objects.get(id=booking_id, user=request.user.customer_profile)
                billing =  Billing.objects.filter(booking=booking).first()
            if not billing and table_id:
                table = Table.objects.get(id=table_id)
                billing = Billing.objects.filter(table=table).first()
            if not billing:
                return Response({"error": "Billing not found for this booking or table."}, status=status.HTTP_404_NOT_FOUND)

            if billing.payment_status != 'success':
                return Response({"error": "Bill is not paid yet."}, status=400)
            billing.complete_order = True
            billing.payment_status = 'paid'
            billing.save()
            if billing.table:
                table = billing.table
                table.booking_status = False
                table.save()

            return Response({
                "message": "Order marked as completed successfully.",
                "booking_id": billing.booking.id if billing.booking else None,
                "table_id": billing.table.id if billing.table else None,
                "final_amount_paid": billing.final_amount_to_pay
            }, status=status.HTTP_200_OK)

        
        except SeatBooking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        except Table.DoesNotExist:
            return Response({"error": "Table not found."}, status=status.HTTP_404_NOT_FOUND)


class ReviewView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        reviews = Review.objects.filter(user=profile)
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Review ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)
            
        review = get_object_or_404(Review, pk=pk, user=profile)
        review.delete()
        return Response({"message": "Review deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class NotificationView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found"}, status=404)

        notifications = Notification.objects.filter(restaurant=restaurant).order_by('-created_at')
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=200)


class AddressView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        addresses = Address.objects.filter(user=profile).order_by('-created_at')
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AddressSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Address ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        address = get_object_or_404(Address, pk=pk)
        serializer = AddressSerializer(address, data=request.data, partial=True)
        if serializer.is_valid():
            updated_address = serializer.save()

            return Response({
                "message": "Address updated successfully.",
                "address": AddressSerializer(updated_address).data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Address ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)     
        address = get_object_or_404(Address, pk=pk, user=request.user.customer_profile)
        address.delete()
        return Response({"message": "Address deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class CancelSeatBookingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get('booking')

        if not booking_id:
            return Response({"error": "Booking ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = SeatBooking.objects.get(id=booking_id, user=request.user.customer_profile)
        except SeatBooking.DoesNotExist:
            return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        slot_start_datetime = timezone.make_aware(datetime.combine(booking.seat_slot.date, booking.seat_slot.start_time))
        time_difference = slot_start_datetime - now
        print("Time difference:", time_difference)
        if time_difference >= timedelta(hours=2):
            booking.payment_status = 'cancelled'
            booking.locked = False
            booking.lock_expiry = None
            booking.save()

            Notification.objects.create(
            restaurant=booking.seat_slot.restaurant, 
            title="Refund Request",
            message=f"Refund ₹{booking.total_advance_payment} to customer {booking.user.user.username} for Booking #{booking.id}."
            )

            return Response({
                "message": "Cancellation successful. Restaurant will refund your amount manually.",
                "refund_eligible": True,
                "amount_to_refund": str(booking.total_advance_payment),
            }, status=status.HTTP_200_OK)

        else:
            return Response({
                "message": "Cancellation late. No refund as per policy.",
                "refund_eligible": False,
            }, status=status.HTTP_400_BAD_REQUEST)

# ── Razorpay ───────────────────────────────────────────────────

class CreateRazorpayOrderView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get('booking_id')

        if not booking_id:
            return Response(
                {"error": "booking_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the booking
        try:
            booking = SeatBooking.objects.get(
                id=booking_id,
                user=request.user.customer_profile
            )
        except SeatBooking.DoesNotExist:
            return Response(
                {"error": "Booking not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Must be pending
        if booking.payment_status != 'pending':
            return Response(
                {"error": f"Booking is already {booking.payment_status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check lock not expired
        if booking.is_lock_expired():
            booking.release_lock()
            return Response(
                {"error": "Booking lock expired. Please book again."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create Razorpay order
        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

        # Amount must be in paise (multiply by 100)
        amount_in_paise = int(booking.total_advance_payment * 100)

        try:
            razorpay_order = client.order.create({
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": f"booking_{booking.id}",
                "notes": {
                    "booking_id": str(booking.id),
                    "restaurant": booking.restaurant.name,
                    "guests": str(booking.number_of_guests),
                }
            })
        except Exception as e:
            return Response(
                {"error": "Failed to create payment order.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {
                "razorpay_order_id": razorpay_order['id'],
                "amount": amount_in_paise,
                "currency": "INR",
                "booking_id": booking.id,
                "razorpay_key": settings.RAZORPAY_KEY_ID,
            },
            status=status.HTTP_200_OK
        )


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(APIView):

    def post(self, request):
        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET  # fixed: separate secret, not API key secret

        razorpay_signature = request.headers.get('X-Razorpay-Signature')
        if not razorpay_signature:
            return Response({"error": "Missing signature."}, status=status.HTTP_400_BAD_REQUEST)

        body = request.body
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'), body, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, razorpay_signature):
            return Response({"error": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(body)
        except Exception:
            return Response({"error": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        event = payload.get('event')
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        notes = payment_entity.get('notes', {})
        payment_type = notes.get('type')  # 'bill_payment' if from CreateBillPaymentOrderView, else seat booking

        if event == 'payment.captured':
            if payment_type == 'bill_payment':
                return self._handle_bill_payment_captured(payment_entity, notes)
            return self._handle_seat_booking_captured(payment_entity, notes)

        if event == 'payment.failed':
            if payment_type == 'bill_payment':
                return self._handle_bill_payment_failed(notes)
            return self._handle_seat_booking_failed(notes)

        return Response({"status": "Event received."}, status=200)

    def _handle_seat_booking_captured(self, payment_entity, notes):
        booking_id = notes.get('booking_id')
        if not booking_id:
            return Response({"error": "booking_id missing in notes."}, status=400)

        with transaction.atomic():
            try:
                booking = SeatBooking.objects.select_for_update().get(id=booking_id)
            except SeatBooking.DoesNotExist:
                return Response({"error": "Booking not found."}, status=404)

            if booking.payment_status == 'success':
                return Response({"status": "Already confirmed."}, status=200)  # idempotent on retries

            if booking.is_lock_expired():
                booking.release_lock()
                return Response({"error": "Booking expired."}, status=400)

            expected_paise = int(round(booking.total_advance_payment * 100))
            received_paise = int(payment_entity.get('amount', 0))
            if received_paise != expected_paise:
                return Response(
                    {"error": "Amount mismatch.", "expected": expected_paise, "received": received_paise},
                    status=400
                )

            booking.payment_status = 'success'
            booking.locked = False
            booking.lock_expiry = None
            booking.save()

        return Response({"status": "Booking confirmed."}, status=200)

    def _handle_seat_booking_failed(self, notes):
        booking_id = notes.get('booking_id')
        if booking_id:
            try:
                booking = SeatBooking.objects.get(id=booking_id)
                booking.release_lock()
            except SeatBooking.DoesNotExist:
                pass
        return Response({"status": "Payment failed, booking released."}, status=200)

    def _handle_bill_payment_captured(self, payment_entity, notes):
        billing_id = notes.get('billing_id')
        if not billing_id:
            return Response({"error": "billing_id missing in notes."}, status=400)

        with transaction.atomic():
            try:
                billing = Billing.objects.select_for_update().get(id=billing_id)
            except Billing.DoesNotExist:
                return Response({"error": "Billing not found."}, status=404)

            if billing.payment_status == 'success':
                return Response({"status": "Already paid."}, status=200)

            expected_paise = int(round(billing.final_amount_to_pay * 100))
            received_paise = int(payment_entity.get('amount', 0))
            if received_paise != expected_paise:
                return Response(
                    {"error": "Amount mismatch.", "expected": expected_paise, "received": received_paise},
                    status=400
                )

            billing.payment_status = 'success'
            billing.save()

        return Response({"status": "Bill payment confirmed."}, status=200)

    def _handle_bill_payment_failed(self, notes):
        billing_id = notes.get('billing_id')
        if billing_id:
            try:
                billing = Billing.objects.get(id=billing_id)
                billing.payment_status = 'failed'
                billing.save()
            except Billing.DoesNotExist:
                pass
        return Response({"status": "Bill payment failed."}, status=200)

class CreateBillPaymentOrderView(APIView):
    """
    Creates a Razorpay order for the dining bill — amount is always looked up
    server-side from the real Billing record, never trusted from the client.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        table_id = request.data.get('table_id')
        booking_id = request.data.get('booking_id')

        if not table_id and not booking_id:
            return Response(
                {"error": "table_id or booking_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        billing = None
        try:
            if booking_id:
                # Ownership check: only the customer who made this booking can pay it
                booking = SeatBooking.objects.get(id=booking_id, user=request.user.customer_profile)
                billing = Billing.objects.filter(booking=booking).first()
            if not billing and table_id:
                # Table-only bills are shared dine-in bills — any diner at that table can pay,
                # which is intentional (no single "owner" of a walk-in table order)
                table = Table.objects.get(id=table_id)
                billing = Billing.objects.filter(table=table).first()
        except SeatBooking.DoesNotExist:
            return Response({"error": "Booking not found or unauthorized."}, status=status.HTTP_404_NOT_FOUND)
        except Table.DoesNotExist:
            return Response({"error": "Table not found."}, status=status.HTTP_404_NOT_FOUND)

        if not billing:
            return Response({"error": "Bill not found. Generate the bill first."}, status=status.HTTP_404_NOT_FOUND)

        if billing.payment_status == 'success':
            return Response({"error": "This bill has already been paid."}, status=status.HTTP_400_BAD_REQUEST)

        amount_rupees = billing.final_amount_to_pay  # Decimal — never client-supplied
        if amount_rupees <= 0:
            return Response({"error": "Nothing to pay for this bill."}, status=status.HTTP_400_BAD_REQUEST)

        amount_in_paise = int(round(amount_rupees * 100))

        notes = {
            "type": "bill_payment",
            "billing_id": str(billing.id),
            "customer": str(request.user.username),
        }

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            razorpay_order = client.order.create({
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": f"bill_{billing.id}_{int(timezone.now().timestamp())}",
                "notes": notes,
            })
        except Exception as e:
            return Response(
                {"error": "Failed to create bill payment order.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        billing.razorpay_order_id = razorpay_order['id']
        billing.save(update_fields=['razorpay_order_id'])

        return Response(
            {
                "razorpay_order_id": razorpay_order['id'],
                "amount": amount_in_paise,
                "currency": "INR",
                "billing_id": billing.id,
                "razorpay_key": settings.RAZORPAY_KEY_ID,
            },
            status=status.HTTP_200_OK
        )