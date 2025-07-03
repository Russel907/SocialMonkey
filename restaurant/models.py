from django.db import models
from datetime import date, datetime
from django.contrib.auth.models import User



class Restaurant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='media/restaurants/')
    location = models.CharField(max_length=500)
    map_link = models.URLField(max_length=1000)
    phone_number = models.CharField(max_length=15)
    owner_name = models.CharField(max_length=255)
    food_type = models.CharField(max_length=255, blank=True, null=True) 
    average_bill_for_two = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class RestaurantStaffProfile(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('server', 'Server'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE,  related_name='staff_profile')
    restaurant = models.ForeignKey('Restaurant', on_delete=models.CASCADE, related_name='staff')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} at {self.restaurant.name}"


class Server(models.Model):
    profile = models.OneToOneField('RestaurantStaffProfile', on_delete=models.CASCADE, related_name='server_profile')
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)

    def clean(self):
        if self.profile and self.profile.role != 'server':
            raise ValidationError("Cannot create Server profile for staff who is not a 'server'.")

    def save(self, *args, **kwargs):
        self.full_clean() 
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} (Server for {self.profile})"


class Menu(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menus')
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='media/menus/', null=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    minimum_wait_time = models.TextField(default="In minutes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.restaurant.name}"


class TableConfig(models.Model):
    restaurant = models.OneToOneField(Restaurant, on_delete=models.CASCADE, related_name='table_config')
    total_tables = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.restaurant.name} - Tables: {self.total_tables}"


class Table(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='tables')
    table_number = models.CharField(max_length=20)
    qr_code = models.ImageField(upload_to='qrcodes/', null=True, blank=True)
    booking_status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Table {self.table_number} ({self.restaurant.name})"


class Payment(models.Model):
    restaurant = models.OneToOneField(Restaurant, on_delete=models.CASCADE, related_name='payment')
    min_advance_amount = models.DecimalField(max_digits=10, decimal_places=2)
    upi_id = models.CharField(max_length=255)
    upi_qr_code = models.ImageField(upload_to='media/upi_qr_codes/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment settings for {self.restaurant.name}"


class Timing(models.Model):
    restaurant = models.OneToOneField('Restaurant', on_delete=models.CASCADE, related_name='timing')
    open_time = models.TimeField()
    close_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.restaurant.name} opens at {self.open_time} and closes at {self.close_time}"


class Seats(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='seats')
    total_seats = models.PositiveIntegerField()
    start_time = models.TimeField()  
    end_time = models.TimeField()    
    interval_minutes = models.PositiveIntegerField() 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.restaurant.name} Seats: {self.total_seats}"


class SeatSlot(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='seat_slots')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    available_seats = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        unique_together = ('restaurant', 'date', 'start_time')

    def __str__(self):
        return f"{self.restaurant.name} Slot on {self.date} from {self.start_time} to {self.end_time}"


class Gallery(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='albums')
    image = models.ImageField(upload_to='media/restaurant_albums/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Image for {self.restaurant.name}"


class Performance(models.Model):
    ENTRY_CHOICES = [
    ('free_entry', 'Free_entry'),
    ('paid_entry', 'Paid_entry'),
    ]
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='performance')
    image = models.ImageField(upload_to='media/performance/', null=True, blank=True)
    name = models.CharField(max_length=255)
    entry = models.CharField(max_length=20, choices=ENTRY_CHOICES, default='free_entry')
    start_time = models.TimeField()
    date = models.DateField()
    entry_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    theme = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Offer(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='offers')
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    valid_from = models.DateField()
    valid_until = models.DateField()
    start_time = models.TimeField(null=True, blank=True)  
    end_time = models.TimeField(null=True, blank=True)    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.discount_percentage}%"

    def save(self, *args, **kwargs):
        self.check_validity()
        super().save(*args, **kwargs)

    def check_validity(self):
        now = datetime.now()
        today = now.date()
        current_time = now.time()

        # Expired by date
        if self.valid_until < today:
            self.is_active = False
            return

        # Expired today but passed end_time
        if self.valid_until == today:
            if self.end_time and current_time > self.end_time:
                self.is_active = False


class DiningOffer(models.Model):
    restaurant = models.ForeignKey('Restaurant', on_delete=models.CASCADE, related_name='dining_offers')
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - ₹{self.amount}"




