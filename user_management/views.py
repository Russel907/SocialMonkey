from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status  
from django.shortcuts import get_object_or_404
from rest_framework.authtoken.models import Token
from decimal import Decimal
from restaurant.models import Table, Restaurant
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from django.db.models import Max, Sum
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
from .serializers import CustomerProfileSerializer, BookingSerializer, MenuBookingSerializer, BillingSerializer, BillingSerializer, SeatBookingSerializer, ReviewSerializer, SpecialRequestForSeatSerializer, SpecialRequestMessageSerializer, NotificationSerializer, AddressSerializer
from restaurant.serializers import TableSerializer, RestaurantSerializer
from .models import CustomerProfile, Booking, MenuBooking, Billing, SeatBooking, Review, SpecialRequestForSeat, SpecialRequestMessage, Notification, Address



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

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RestaurantListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurants = Restaurant.objects.all()
        serializer = RestaurantSerializer(restaurants, many=True)
        return Response(serializer.data)


class BookingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        bookings = Booking.objects.filter(user=profile).order_by('-booking_date')
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)

    def post(self, request):
        table_id = request.data.get('table')
        try:
            table = Table.objects.get(id=table_id)
            if table.booking_status:
                return Response({"error": "This table is already booked."}, status=status.HTTP_400_BAD_REQUEST)
        except Table.DoesNotExist:
            return Response({"error": "Table not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            return Response({"error": "Customer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookingSerializer(data=request.data)
        if serializer.is_valid():
            restaurant_id = request.data.get('restaurant')

            # Mark table as booked
            table.booking_status = True
            table.save()

            # Save booking
            serializer.save(user=profile, restaurant_id=restaurant_id, table_id=table.id)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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


class AvailableTableByRestaurent(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        restaurant_id = request.data.get('restaurant_id')

        if not restaurant_id:
            return Response({"error": "Restaurant ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        restaurant = get_object_or_404(Restaurant, id=restaurant_id)
        tables = Table.objects.filter(restaurant=restaurant, booking_status=False)
        serializer = TableSerializer(tables, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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


class SpecialRequestForSeatView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get('booking')
        message = request.data.get('message')

        if not booking_id or not message:
            return Response({"error": "Booking ID and message are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = MenuBooking.objects.get(id=booking_id, user=request.user.customer_profile)
            special_request, created = SpecialRequestForSeat.objects.get_or_create(booking=booking, defaults={'message': message})
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

        special_requests = SpecialRequestForSeat.objects.filter(booking__user=profile)
        serializer = SpecialRequestForSeatSerializer(special_requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
            available = booking.seat_slot.total_seats - total_taken

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
        booking_id = request.data.get("booking_id")
        payment_status = request.data.get("payment_status")  # 'success' or 'failed'

        if not booking_id or payment_status not in ['success', 'failed']:
            return Response({"error": "Invalid data provided."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                booking = SeatBooking.objects.select_for_update().get(id=booking_id, user=request.user.customer_profile)
            except SeatBooking.DoesNotExist:
                return Response({"error": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

            now = timezone.now()

            if booking.is_lock_expired():
                booking.release_lock()
                return Response({"error": "Booking expired."}, status=status.HTTP_400_BAD_REQUEST)

            if payment_status == 'failed':
                booking.release_lock()
                return Response({"status": "Payment failed, booking released."}, status=status.HTTP_400_BAD_REQUEST)

            # Confirm fresh availability
            confirmed = SeatBooking.objects.filter(
                seat_slot=booking.seat_slot,
                payment_status='success'
            ).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            locked = SeatBooking.objects.filter(
                seat_slot=booking.seat_slot,
                locked=True,
                lock_expiry__gt=now
            ).exclude(id=booking.id).aggregate(Sum('number_of_guests'))['number_of_guests__sum'] or 0

            total_taken = confirmed + locked
            available = booking.seat_slot.available_seats - total_taken

            if available >= booking.number_of_guests:
                booking.payment_status = 'success'
                booking.locked = False
                booking.lock_expiry = None
                booking.save()
                return Response({"status": "Booking confirmed!"})
            else:
                booking.release_lock()
                return Response({"error": "Seats not available anymore."}, status=status.HTTP_400_BAD_REQUEST)


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

            billing.complete_order = True
            billing.save()

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