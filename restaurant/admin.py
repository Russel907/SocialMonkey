from django.contrib import admin
from .models import Restaurant, Menu, Table, Payment, Seats, SeatSlot, Gallery, Performance, Offer, DiningOffer, TableConfig, RestaurantStaffProfile, Server

admin.site.register(Restaurant)
admin.site.register(Menu)   
admin.site.register(Table)
admin.site.register(Payment) 
admin.site.register(Seats)   
admin.site.register(SeatSlot)
admin.site.register(Gallery)
admin.site.register(Performance)
admin.site.register(Offer)
admin.site.register(DiningOffer)
admin.site.register(TableConfig)
admin.site.register(RestaurantStaffProfile)
admin.site.register(Server)