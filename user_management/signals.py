from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification, SpecialRequestMessage



@receiver(post_save, sender=SpecialRequestMessage)
def create_notification(sender, instance, created, **kwargs):
    if created:
        menu_booking = instance.booking
        restaurant = menu_booking.booking.restaurant
        table_number = menu_booking.table.table_number

        title = "New Special Request"
        message = f"Special request from Table {table_number}: \"{instance.message}\""
        print("Notification created:", message)  
        Notification.objects.create(
            restaurant=restaurant,
            title=title,
            message=message,
        )

