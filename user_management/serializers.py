import re
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import CustomerProfile, Booking, MenuBooking, Billing, SeatBooking, Review, SpecialRequestForSeat, SpecialRequestMessage, Notification, Address


class CustomerProfileSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(write_only=True)  # Incoming phone number
    username = serializers.CharField(source='user.username', read_only=True)  # Show username in response

    class Meta:
        model = CustomerProfile
        fields = ['id', 'phone_number', 'username', 'full_name', 'gender', 'profile_picture','is_verified']

    def validate_phone_number(self, value):
        if not re.match(r'^[6-9]\d{9}$', value):
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")
        if self.instance and self.instance.user.username == value:
            return value
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def create(self, validated_data):
        phone_number = validated_data.pop('phone_number')
        user = User.objects.create(username=phone_number)
        profile = CustomerProfile.objects.create(user=user, **validated_data)
        return profile


class BookingSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='user.full_name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    table_number = serializers.CharField(source='table.table_number', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'customer_name', 'restaurant_name', 'table_number',
            'booking_date', 'advance_payment', 'payment_status',
            'status', 'special_request', 'created_at', 'updated_at'
        ]
        

class MenuBookingSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source='menu.name', read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = MenuBooking
        fields = ['id','booking','menu','menu_name','quantity','special_note','table','total_price','created_at','updated_at']

    def get_total_price(self, obj):
        return obj.quantity * obj.menu.price\


class BillingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Billing
        fields = ['id','booking','table','total_menu_price','final_amount_to_pay','created_at',]
        read_only_fields = ['total_menu_price','final_amount_to_pay','created_at',]


class SeatBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeatBooking
        fields = '__all__'
        read_only_fields = ['total_advance_payment', 'user', 'queue_priority']


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'restaurant', 'stars', 'description']


class SpecialRequestForSeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecialRequestForSeat
        fields = ['id', 'message', 'booking']
        read_only_fields = ['id', 'booking']


class SpecialRequestMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecialRequestMessage
        fields = ['id', 'message', 'booking']
        read_only_fields = ['id', 'booking']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields=['id','restaurant','title','message','is_read']
        read_only_fields=['id','restaurant']


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'user', 'address_type', 'street_address', 'city', 'state', 'postal_code']
        read_only_fields = ['id', 'user']