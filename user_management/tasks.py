from django.test import TestCase

# Create your tests here.
from celery import shared_task
from django.utils import timezone
from user_management.models import SeatBooking

@shared_task
def cleanup_expired_bookings():
    now = timezone.now()
    expired = SeatBooking.objects.filter(
        locked=True,
        payment_status='pending',
        lock_expiry__lt=now
    )
    count = expired.count()

    for booking in expired:
        seat_slot = booking.seat_slot
        seat_slot.available_seats += booking.number_of_guests
        seat_slot.save()

        booking.locked = False
        booking.payment_status = 'failed'
        booking.lock_expiry = None
        booking.save()

    return f"{count} expired bookings released."
