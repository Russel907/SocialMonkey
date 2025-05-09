from django.contrib import admin
from .models import CustomerProfile, Booking, MenuBooking, Billing, SeatBooking, SpecialRequestForSeat, SpecialRequestMessage, Review, Notification, Address

admin.site.register(CustomerProfile)
admin.site.register(Booking)
admin.site.register(MenuBooking)
admin.site.register(Billing) 
admin.site.register(SeatBooking)   
admin.site.register(SpecialRequestForSeat)
admin.site.register(SpecialRequestMessage)
admin.site.register(Review)
admin.site.register(Notification)
admin.site.register(Address)
# admin.site.register(server)

