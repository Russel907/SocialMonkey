from django.db import models
from django.contrib.auth.models import User
from restaurant.models import Restaurant, Table, Menu, Payment, Timing, SeatSlot, Offer, Payment
from decimal import Decimal
from django.utils import timezone



class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    full_name = models.CharField(max_length=255)
    gender = models.CharField(
        max_length=50,
        choices=[('male', 'Male'), ('female', 'Female'), ('non-binary', 'Non-binary'), ('prefer-not-to-say', 'Prefer-not-to-say')],
        blank=True
    )
    profile_picture = models.ImageField(upload_to='media/customer_profiles/', null=True, blank=True)
    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name


class Booking(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    user = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='bookings')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='bookings')
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, related_name='bookings')
    booking_date = models.DateField()
    advance_payment = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    special_request = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking by {self.user.full_name} at {self.restaurant.name} on {self.booking_date}"


class SeatBooking(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='seat_bookings')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='seat_bookings')  
    seat_slot = models.ForeignKey(SeatSlot, on_delete=models.CASCADE, related_name='seat_bookings')     
    offer = models.ForeignKey(Offer, on_delete=models.SET_NULL, null=True, blank=True)                  

    number_of_guests = models.PositiveIntegerField()
    total_advance_payment = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    locked = models.BooleanField(default=True)  
    lock_expiry = models.DateTimeField(null=True, blank=True)

    queue_priority = models.PositiveIntegerField(null=True, blank=True)  

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_total_payment(self):
        try:
            per_guest = self.restaurant.payment.min_advance_amount
        except Payment.DoesNotExist:
            per_guest = Decimal('0.00')

        total = per_guest * self.number_of_guests

        if self.offer and self.offer.is_active:
            total -= total * (self.offer.discount_percentage / Decimal(100))

        self.total_advance_payment = total
        return total

    def is_lock_expired(self):
        return self.locked and self.lock_expiry and timezone.now() > self.lock_expiry

    def release_lock(self):
        self.locked = False
        self.lock_expiry = None
        self.payment_status = 'failed'
        self.save()

    def __str__(self):
        return f"{self.user.full_name} - {self.number_of_guests} guests at {self.restaurant.name} on {self.seat_slot.date}"


class MenuBooking(models.Model):
    booking = models.ForeignKey(SeatBooking, on_delete=models.CASCADE, related_name='menu_items', null=True, blank=True)
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='menu_bookings')
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name='menu_bookings')
    quantity = models.PositiveIntegerField(default=1)
    special_note = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_price(self):
        return self.menu.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.menu.name} for booking #{self.booking.id}"


class Billing(models.Model):
    booking = models.OneToOneField(SeatBooking, on_delete=models.CASCADE, related_name='billing', null=True, blank=True)
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='menu_billings')
    total_menu_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_amount_to_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    complete_order = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_total_menu_price(self):
        if self.booking:
            total = sum(item.total_price() for item in self.booking.menu_items.all())
        else:
            total = sum(item.total_price() for item in self.table.menu_bookings.all())
        self.total_menu_price = total
        return total

    def calculate_final_amount(self):
        self.calculate_total_menu_price()
        if self.booking:
            self.final_amount_to_pay = max(self.total_menu_price - self.booking.total_advance_payment, 0)
        else:
            self.final_amount_to_pay = self.total_menu_price
        return self.final_amount_to_pay

    def release_table_if_completed(self):
        if self.complete_order:
            table=self.table
            table.booking_status = False
            table.save()

    def save(self, *args, **kwargs):
        self.calculate_final_amount()
        super().save(*args, **kwargs)
        self.release_table_if_completed()

    def __str__(self):
        return f"Billing for table #{self.table.id} - Final: ₹{self.final_amount_to_pay}"


class Review(models.Model):
    user = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='reviews')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='reviews')
    stars = models.PositiveIntegerField()
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stars} ★ for {self.restaurant.name}"
        

class SpecialRequestForSeat(models.Model):
    booking = models.OneToOneField(SeatBooking, on_delete=models.CASCADE, related_name='special_request')
    message = models.TextField(blank=True, null=True)  
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SpecialRequestMessage(models.Model):
    booking = models.OneToOneField('MenuBooking', on_delete=models.CASCADE, related_name='special_request_message')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Request from Table {self.booking.table.table_number}"


class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
    ('special_request', 'Special Request'),
    ('refund_request', 'Refund Request'),
    ]

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES, default='special_request')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification for {self.restaurant.name}: {self.title}"


class Address(models.Model):
    ADDRESS_TYPE_CHOICES = [
        ('home', 'Home'),
        ('work', 'Work'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='Address')
    address_type = models.CharField(max_length=10, choices=ADDRESS_TYPE_CHOICES, default='home')
    street_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_address_type_display()} Address"


