import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from user_management.models import SeatBooking

class Command(BaseCommand):
    help = 'Continuously clean expired bookings every 10 minutes'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("⏳ Started seat booking cleaner loop..."))

        while True:
            now = timezone.now()
            expired = SeatBooking.objects.filter(
                locked=True,
                lock_expiry__lt=now,
                payment_status='pending'
            )

            count = expired.count()

            for booking in expired:
                booking.seat_slot.available_seats += booking.number_of_guests
                booking.seat_slot.save()
                booking.locked = False
                booking.payment_status = 'failed'
                booking.lock_expiry = None
                booking.save()
                booking.delete()

            self.stdout.write(f"[{timezone.now()}] ✅ Cleaned {count} expired bookings.")
            time.sleep(8000)  
