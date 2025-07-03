import re
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Restaurant, Menu, Table, Payment, Timing, Seats, SeatSlot, Gallery, Performance, Offer, DiningOffer, TableConfig, RestaurantStaffProfile, Server




class RestaurantSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Restaurant
        fields = ['id', 'name', 'image', 'location', 'map_link', 'phone_number', 'owner_name', 'email', 'password', 'food_type','average_bill_for_two']

    def validate_email(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_phone_number(self, value):
        if not re.match(r'^[6-9]\d{9}$', value):
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")

        if Restaurant.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")

        return value

    def validate_password(self, value):
        if len(value) < 8 or \
           not re.search(r'[A-Z]', value) or \
           not re.search(r'[a-z]', value) or \
           not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError("Password must be at least 8 characters with upper, lower, special char.")
        return value

    def create(self, validated_data):
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        user = User.objects.create_user(username=email, email=email, password=password)
        restaurant = Restaurant.objects.create(user=user, **validated_data)
        RestaurantStaffProfile.objects.create(user=user, restaurant=restaurant, role='owner')
        return restaurant


    def update(self, instance, validated_data):
        user = instance.user
        email = validated_data.pop('email', None)
        password = validated_data.pop('password', None)

        if email:
            user.username = email
            user.email = email
        if password:
            user.set_password(password)
        user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class serverSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    re_enter_password = serializers.CharField(write_only=True)
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    email = serializers.EmailField()

    def validate_email(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_phone_number(self, value):
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("Enter a valid 10-digit phone number.")
        if Server.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already in use.")
        return value

    def validate(self, data):
        if data['password'] != data['re_enter_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        owner = request.user

        if not hasattr(owner, 'staff_profile') or owner.staff_profile.role not in ['owner', 'manager']:
            raise serializers.ValidationError("Only owner or manager can create server accounts.")
        restaurant = owner.staff_profile.restaurant

        email = validated_data['email']
        password = validated_data['password']

        user = User.objects.create_user(
            username=email,
            password=password,
            email=email
        )

        staff_profile = RestaurantStaffProfile.objects.create(
            user=user,
            restaurant=restaurant,
            role='server'
        )

        Server.objects.create(
            profile=staff_profile,
            full_name=validated_data['full_name'],
            phone_number=validated_data['phone_number']
        )

        return user



class MenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Menu
        fields = ['id', 'name', 'image', 'description', 'price', 'minimum_wait_time', 'created_at']


class TableConfigSerializer(serializers.ModelSerializer):  
    class Meta:
        model = TableConfig
        fields = ['id', 'restaurant', 'total_tables']
        read_only_fields = ['restaurant']

    def validate_total_tables(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total tables must be a positive integer.")
        return value


class TableSerializer(serializers.ModelSerializer):
    table_number = serializers.CharField(max_length=20, required=True)

    class Meta:
        model = Table   
        fields = ['id', 'table_number', 'qr_code', 'booking_status']

    def validate_table_number(self, value):
        if Table.objects.filter(table_number=value).exists():
            raise serializers.ValidationError("This table number is already registered.")
        return value


class SeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seats
        fields = ['id', 'total_seats', 'start_time', 'end_time', 'interval_minutes']

    def validate(self, data):
        # Use instance values if fields are not in data (for partial updates)
        start_time = data.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = data.get('end_time', getattr(self.instance, 'end_time', None))
        restaurant = getattr(self.instance, 'restaurant', None) or data.get('restaurant')

        # Only validate time comparison if both are present
        if start_time and end_time:
            if start_time >= end_time:
                raise serializers.ValidationError("End time must be after start time.")
        elif 'start_time' in data or 'end_time' in data:
            raise serializers.ValidationError("Both start_time and end_time are required to update time range.")

        if start_time and end_time and Seats.objects.filter(
            restaurant=restaurant,
            start_time=start_time,
            end_time=end_time
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A seat configuration with this time range already exists for this restaurant.")

        return data

class PaymentSerializer(serializers.ModelSerializer):
    upi_id = serializers.CharField(max_length=255, required=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'min_advance_amount', 'upi_id', 'upi_qr_code', 'restaurant_name']

    def validate_upi_id(self, value):
        pattern = r'^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$'
        if not re.match(pattern, value):
            raise serializers.ValidationError("Enter a valid UPI ID (e.g., name@bank).")
        return value


class TimingSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    open_time = serializers.TimeField()
    close_time = serializers.TimeField()

    class Meta:
        model = Timing
        fields = ['id', 'open_time', 'close_time','restaurant_name']

    def validate(self, data):
        open_time = data.get('open_time')
        close_time = data.get('close_time')

        if open_time and close_time and open_time >= close_time:
            raise serializers.ValidationError("Open time must be before close time.")

        return data


class SeatSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeatSlot
        fields = ['id', 'restaurant', 'date', 'start_time', 'end_time', 'available_seats']
        read_only_fields = ['restaurant']


class GallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Gallery
        fields = ['id', 'restaurant','image', 'uploaded_at']
        read_only_fields = ['restaurant']


class Performanceserializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = ['id', 'restaurant', 'entry','theme', 'date', 'entry_fee', 'start_time','image']
        read_only_fields = ['restaurant']


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ['id', 'restaurant', 'title', 'discount_percentage', 'description', 'valid_from', 'valid_until', 'start_time','end_time', 'is_active']
        read_only_fields = ['restaurant']


class DiningOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiningOffer
        fields = ['id', 'restaurant', 'title', 'description', 'amount']
        read_only_fields = ['restaurant']


