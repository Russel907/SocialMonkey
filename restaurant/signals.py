import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Seats, SeatSlot, Table, TableConfig
from user_management.models import MenuBooking

@receiver(post_save, sender=Seats)
def create_or_update_seat_slots(sender, instance, created, **kwargs):
    today = timezone.now().date()

    # Optional: delete old slots if you want to regenerate
    SeatSlot.objects.filter(restaurant=instance.restaurant, date=today).delete()

    start_datetime = datetime.combine(today, instance.start_time)
    end_datetime = datetime.combine(today, instance.end_time)
    interval = timedelta(minutes=instance.interval_minutes)

    while start_datetime < end_datetime:
        slot_start = start_datetime.time()
        slot_end = (start_datetime + interval).time()

        SeatSlot.objects.create(
            restaurant=instance.restaurant,
            date=today,
            start_time=slot_start,
            end_time=slot_end,
            available_seats=instance.total_seats
        )
        start_datetime += interval

@receiver(post_save, sender=TableConfig)
def generate_or_trim_tables(sender, instance, created, **kwargs):
    restaurant = instance.restaurant
    existing_tables = restaurant.tables.all().order_by('id')  
    existing_count = existing_tables.count()
    target_count = instance.total_tables

    if target_count > existing_count:
        for i in range(existing_count + 1, target_count + 1):
            table_number = f"TBL-{i:03d}"
            qr_data = f"{restaurant.name} - Table {table_number}"

            qr = qrcode.make(qr_data)
            buffer = BytesIO()
            qr.save(buffer)
            buffer.seek(0)

            filename = f"{restaurant.name}_table_{table_number}.png"
            filebuffer = ContentFile(buffer.getvalue(), name=filename)

            Table.objects.create(
                restaurant=restaurant,
                table_number=table_number,
                qr_code=filebuffer
            )

    elif target_count < existing_count:
        tables_to_delete = existing_tables.reverse()[:existing_count - target_count]
        for table in tables_to_delete:
            table.delete()
