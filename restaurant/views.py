from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.timezone import localtime
from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from .models import Restaurant, Menu, Table, TableConfig, Payment, Timing, Seats, SeatSlot, Gallery, Performance, Offer, DiningOffer, TableConfig, RestaurantStaffProfile, Server
from .serializers import RestaurantSerializer, MenuSerializer, TableSerializer, PaymentSerializer, TimingSerializer, SeatSerializer, SeatSlotSerializer, GallerySerializer, Performanceserializer, OfferSerializer, DiningOfferSerializer, TableConfigSerializer, serverSerializer
from user_management.models import MenuBooking, SpecialRequestMessage, SeatBooking, SpecialRequestForSeat

class RestaurantRegisterView(APIView):
    def post(self, request):
        serializer = RestaurantSerializer(data=request.data)
        if serializer.is_valid():
            restaurant = serializer.save()
            token, _ = Token.objects.get_or_create(user=restaurant.user)
            return Response({
                'message': 'Restaurant registered successfully',
                'token': token.key,
                'restaurant': serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        restaurants = Restaurant.objects.all()
        serializer = RestaurantSerializer(restaurants, many=True)
        return Response(serializer.data)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Restaurant ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        restaurant = get_object_or_404(Restaurant, pk=pk)
        serializer = RestaurantSerializer(restaurant, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Restaurant profile updated successfully',
                'restaurant': serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RestaurantLoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        print(email, password)
        user = authenticate(username=email, password=password)
        print("Authenticated user:", user)

        if not user:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        token, _ = Token.objects.get_or_create(user=user)

        # ✅ Check if user is restaurant owner (linked to Restaurant model)
        if hasattr(user, 'restaurant'):
            restaurant = user.restaurant
            serializer = RestaurantSerializer(restaurant)
            return Response({
                'message': 'Login successful (restaurant owner)',
                'token': token.key,
                'role': 'owner',
                'email': email,
                'restaurant': serializer.data
            }, status=status.HTTP_200_OK)

        # ✅ Check if user is restaurant staff (e.g., server, manager)
        elif hasattr(user, 'staff_profile'):
            staff = user.staff_profile
            return Response({
                'message': f'Login successful ({staff.role})',
                'token': token.key,
                'role': staff.role,
                'restaurant_id': staff.restaurant.id,
                'restaurant_name': staff.restaurant.name,
                'username': user.username
            }, status=status.HTTP_200_OK)

        return Response({'error': 'User is not assigned to any restaurant or staff profile.'}, status=status.HTTP_403_FORBIDDEN)


class CreateServerView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'staff_profile') or request.user.staff_profile.role not in ['owner', 'manager']:
            return Response({'error': 'Only owners or managers can view servers.'}, status=status.HTTP_403_FORBIDDEN)

        restaurant = request.user.staff_profile.restaurant
        servers = Server.objects.filter(profile__restaurant=restaurant)
        data = [{
            'id': s.profile.user.id,
            'full_name': s.full_name,
            'phone_number': s.phone_number,
            'role': s.profile.role,
            'email': s.profile.user.email,
        } for s in servers]

        return Response(data)

    def post(self, request):
        serializer = serverSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save()
            staff_profile = user.staff_profile 

            return Response({
                'message': 'Server account created successfully.',
                'server_username': user.username,
                'server_phone_number': request.data.get('phone_number'),
                'server_full_name': request.data.get('full_name'),
                'server_role': staff_profile.role,
                'server_id': user.id,
                'server_email': user.email,
                'server_password': request.data.get('password')  
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServerDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        user = get_object_or_404(User, pk=pk)
        staff_profile = get_object_or_404(RestaurantStaffProfile, user=user, role='server')
        server = get_object_or_404(Server, profile=staff_profile)
        return user, staff_profile, server

    def get(self, request, pk):
        user, staff_profile, server = self.get_object(pk)
        return Response({
            'server_id': user.id,
            'server_username': user.username,
            'server_email': user.email,
            'full_name': server.full_name,
            'phone_number': server.phone_number,
            'server_password': user.password,
            'role': staff_profile.role,
        })

    def put(self, request, pk):
        user, staff_profile, server = self.get_object(pk)

        # Validate unique phone number
        new_phone = request.data.get('phone_number', server.phone_number)
        if Server.objects.filter(phone_number=new_phone).exclude(id=server.id).exists():
            return Response({"error": "Phone number already in use."}, status=status.HTTP_400_BAD_REQUEST)

        user.username = request.data.get('username', user.username)
        user.email = request.data.get('email', user.email)
        if request.data.get('password'):
            user.set_password(request.data.get('password'))
        user.save()

        server.full_name = request.data.get('full_name', server.full_name)
        server.phone_number = new_phone
        server.save()

        return Response({
            'message': 'Server profile updated.',
            'server_username': user.username,
            'full_name': server.full_name,
            'phone_number': server.phone_number
        })


    def delete(self, request, pk):
        user, staff_profile, server = self.get_object(pk)
        server.delete()
        staff_profile.delete()
        user.delete()
        return Response({"message": "Server account deleted."}, status=status.HTTP_204_NO_CONTENT)


class MenuCreateListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = MenuSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        menus = Menu.objects.filter(restaurant=restaurant)
        serializer = MenuSerializer(menus, many=True)
        return Response(serializer.data)


    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Menu ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        menu = get_object_or_404(Menu, pk=pk, restaurant=restaurant)

        image_file = request.FILES.get('image')
        if image_file:
            print(f"Image received: name={image_file.name}, content_type={image_file.content_type}, size={image_file.size}")
        else:
            print("No image received or image field missing in request.FILES")


        serializer = MenuSerializer(menu, data=request.data, partial=True)  # partial=True for partial update
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Menu updated successfully",
                "menu": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Menu ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        menu = get_object_or_404(Menu, pk=pk, restaurant=restaurant)
        menu.delete()
        return Response({"message": "Menu item deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class TableConfigView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TableConfigSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        table_config = TableConfig.objects.filter(restaurant=restaurant).first()
        if table_config:
            serializer = TableConfigSerializer(table_config)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response({"error": "Table configuration not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            table_config = TableConfig.objects.get(restaurant=restaurant)
        except TableConfig.DoesNotExist:
            return Response({"error": "Table configuration not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TableConfigSerializer(table_config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)  
    
    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Table ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        tableconfig = get_object_or_404(TableConfig, pk=pk, restaurant=restaurant)
        tableconfig.delete()
        return Response({"message": "Table deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class TableCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TableSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        tables = Table.objects.filter(restaurant=restaurant)
        serializer = TableSerializer(tables, many=True)
        return Response(serializer.data)
   
    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Table ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        table = get_object_or_404(Table, pk=pk, restaurant=restaurant)

        serializer = TableSerializer(table, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Table updated successfully",
                "table": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
   
    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Table ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        table = get_object_or_404(Table, pk=pk, restaurant=restaurant)
        table.delete()
        return Response({"message": "Table deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        

class PaymentCreateView(APIView):
    authentication_classes = [TokenAuthentication] 
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if hasattr(restaurant, 'payment'):
            return Response(
                {"error": "Payment details already exist for this restaurant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PaymentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
   
    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user) 
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)   

        payments = Payment.objects.filter(restaurant=restaurant)
        serializer = PaymentSerializer(payments, many=True) 
        return Response(serializer.data)
   
    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Payment ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)  
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)       

        payment = get_object_or_404(Payment, pk=pk, restaurant=restaurant)
        serializer = PaymentSerializer(payment, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Payment settings updated successfully",
                "payment": serializer.data
            }, status=status.HTTP_200_OK) 

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
   
    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Payment ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST) 
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND) 

        payment = get_object_or_404(Payment, pk=pk, restaurant=restaurant)
        payment.delete()
        return Response({"message": "Payment settings deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class TimingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if hasattr(restaurant, 'timing'):
            return Response(
                {"error": "Timing already exists for this restaurant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = TimingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            timing = restaurant.timing
        except Timing.DoesNotExist:
            return Response({"error": "Timing not set for this restaurant."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TimingSerializer(timing)
        return Response(serializer.data)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Timing ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        timing = get_object_or_404(Timing, pk=pk, restaurant=restaurant)
        serializer = TimingSerializer(timing, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Timing updated successfully.",
                "timing": serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Timing ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        timing = get_object_or_404(Timing, pk=pk, restaurant=restaurant)
        timing.delete()
        return Response({"message": "Timing deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class SeatsCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SeatSerializer(data=request.data)
        if serializer.is_valid():
            seats_instance = serializer.save(restaurant=restaurant)

            # Auto-generate today's seat slots
            today = timezone.now().date()
            start_datetime = datetime.combine(today, seats_instance.start_time)
            end_datetime = datetime.combine(today, seats_instance.end_time)
            interval = timedelta(minutes=seats_instance.interval_minutes)

            while start_datetime < end_datetime:
                slot_start = start_datetime.time()
                slot_end = (start_datetime + interval).time()

                SeatSlot.objects.get_or_create(
                    restaurant=restaurant,
                    date=today,
                    start_time=slot_start,
                    end_time=slot_end,
                    defaults={'available_seats': seats_instance.total_seats}
                )
                start_datetime += interval

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        seats = Seats.objects.filter(restaurant=restaurant)
        serializer = SeatSerializer(seats, many=True)
        return Response(serializer.data)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Seats ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        seat = get_object_or_404(Seats, pk=pk, restaurant=restaurant)
        serializer = SeatSerializer(seat, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Seat configuration updated successfully",
                "seats": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Seats ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        seat = get_object_or_404(Seats, pk=pk, restaurant=restaurant)
        seat.delete()
        return Response({"message": "Seat configuration deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class SeatSlotView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        slots = SeatSlot.objects.filter(restaurant=restaurant)
        serializer = SeatSlotSerializer(slots, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Slot ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        slot = get_object_or_404(SeatSlot, pk=pk, restaurant=restaurant)
        serializer = SeatSlotSerializer(slot, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Slot updated successfully",
                "slot": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Slot ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        slot = get_object_or_404(SeatSlot, pk=pk, restaurant=restaurant)
        slot.delete()
        return Response({"message": "Slot deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class GalleryView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GallerySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        gallery = Gallery.objects.filter(restaurant=restaurant)
        serializer = GallerySerializer(gallery, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Gallery ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        gallery = get_object_or_404(Gallery, pk=pk, restaurant=restaurant)
        gallery.delete()
        return Response({"message": "Gallery deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class PerformanceView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = Performanceserializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        performances = Performance.objects.filter(restaurant=restaurant)
        serializer = Performanceserializer(performances, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Performance ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        performance = get_object_or_404(Performance, pk=pk, restaurant=restaurant)
        performance.delete()
        return Response({"message": "Performance deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Performance ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        performance = get_object_or_404(Performance, pk=pk, restaurant=restaurant)
        serializer = Performanceserializer(performance, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Performance updated successfully",
                "performance": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OfferView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = OfferSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        offers = Offer.objects.filter(restaurant=restaurant)
        serializer = OfferSerializer(offers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Offer ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        offer = get_object_or_404(Offer, pk=pk, restaurant=restaurant)
        offer.delete()
        return Response({"message": "Offer deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Offer ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        offer = get_object_or_404(Offer, pk=pk, restaurant=restaurant)
        serializer = OfferSerializer(offer, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Offer updated successfully",
                "offer": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DiningOfferView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DiningOfferSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        dining_offers = DiningOffer.objects.filter(restaurant=restaurant)
        serializer = DiningOfferSerializer(dining_offers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"error": "Dining Offer ID (pk) is required to delete."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        dining_offer = get_object_or_404(DiningOffer, pk=pk, restaurant=restaurant)
        dining_offer.delete()
        return Response({"message": "Dining Offer deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "Dining Offer ID (pk) is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant profile not found."}, status=status.HTTP_404_NOT_FOUND)

        dining_offer = get_object_or_404(DiningOffer, pk=pk, restaurant=restaurant)
        serializer = DiningOfferSerializer(dining_offer, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Dining Offer updated successfully",
                "dining_offer": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class TableOrderListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found."}, status=404)

        menu_bookings = MenuBooking.objects.filter(table__restaurant=restaurant).select_related(
            'booking__user__user', 'menu', 'table'
        )

        grouped_orders = {}

        for booking in menu_bookings:
            key = f"{booking.table.id}_{booking.booking.id if booking.booking else 'null'}"

            if key not in grouped_orders:
                special_request = SpecialRequestMessage.objects.filter(booking__table=booking.table).first()

                grouped_orders[key] = {
                    "table_no": booking.table.table_number,
                    "user": booking.booking.user.user.username if booking.booking else None,
                    "user_phone": booking.booking.user.user.username if booking.booking else None,
                    "created_at": localtime(booking.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                    "special_request": special_request.message if special_request else "",
                    "menu": [],
                    "total_bill": 0
                }

            grouped_orders[key]["menu"].append({
                "menu_name": booking.menu.name,
                "qty": booking.quantity,
                "price": booking.menu.price,
                "total": booking.quantity * booking.menu.price
            })

            grouped_orders[key]["total_bill"] += booking.quantity * booking.menu.price

        return Response(list(grouped_orders.values()), status=200)



class SeatOrderListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(user=request.user)
        except Restaurant.DoesNotExist:
            return Response({"error": "Restaurant not found."}, status=404)

        seat_bookings = SeatBooking.objects.filter(restaurant=restaurant).select_related(
            'user__user', 'seat_slot'
        )

        data = []
        for booking in seat_bookings:
            data.append({
                "booking_id": booking.id,
                "number_of_guests": booking.number_of_guests,
                "date": booking.seat_slot.date.strftime("%Y-%m-%d"),
                "time_slot": f"{booking.seat_slot.start_time.strftime('%H:%M')} - {booking.seat_slot.end_time.strftime('%H:%M')}",
                "user_phone_number": booking.user.user.username
            })
        return Response(data, status=200)


class SeatBookingDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        booking = get_object_or_404(SeatBooking.objects.select_related('user__user', 'seat_slot', 'restaurant'), pk=pk)

        if booking.restaurant.user != request.user:
            return Response({"error": "You are not authorized to view this booking."}, status=HTTP_404_NOT_FOUND)

        special_request_seat = SpecialRequestForSeat.objects.filter(booking=booking).first()

        data = {
            "booking_id": booking.id,
            "restaurant": booking.restaurant.name,
            "number_of_guests": booking.number_of_guests,
            "date": booking.seat_slot.date.strftime("%Y-%m-%d"),
            "time_slot": f"{booking.seat_slot.start_time.strftime('%H:%M')} - {booking.seat_slot.end_time.strftime('%H:%M')}",
            "user_phone_number": booking.user.user.username,
            "total_advance_payment": str(booking.total_advance_payment),
            "payment_status": booking.payment_status,
            "special_request": special_request_seat.message if special_request_seat else ""
        }

        return Response(data, status=200)
