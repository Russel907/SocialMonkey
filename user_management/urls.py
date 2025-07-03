from django.contrib import admin
from django.urls import path
from .views import CustomerProfileView, EditProfile, MenuBookingView, BillingView, RestaurantListView, SeatBookingView, ReviewView, ConfirmPaymentView, SpecialRequestForSeatView, SpecialRequestMessageView, NotificationView, AddressView, CompleteOrderView, CancelSeatBookingView

urlpatterns = [
    path('login/', CustomerProfileView.as_view(), name="login"),
    path('edit_profile/<int:pk>/', EditProfile.as_view(), name='profile-update'),
    path('restaurant_list/', RestaurantListView.as_view(), name='restaurant_list'),
    path('menu_bookings/', MenuBookingView.as_view(), name='menu-bookings'),
    path('menu_bookings/<int:pk>/', MenuBookingView.as_view(), name='menu-bookings-detail'),
    path('billing/', BillingView.as_view(), name='billing'),
    path('billing/<int:pk>/', BillingView.as_view(), name='billing-detail'),
    path('seat_booking/', SeatBookingView.as_view(), name='seat-booking'),
    path('seat_booking/<int:pk>/', SeatBookingView.as_view(), name='seat-booking-detail'),
    path('review/', ReviewView.as_view(), name='review'),
    path('review/<int:pk>/', ReviewView.as_view(), name='review-detail'),
    path('confirm-payment/', ConfirmPaymentView.as_view(), name='confirm-payment'),
    path('special_request_for_seat/', SpecialRequestForSeatView.as_view(), name='special-request-for-seat'),
    path('special_request_message/', SpecialRequestMessageView.as_view(), name='special-request-message'),
    path('special_request_message/<int:pk>/', SpecialRequestMessageView.as_view(), name='special-request-message-detail'),
    path('notification/', NotificationView.as_view(), name='notification'),
    path('address/', AddressView.as_view(), name='address'),
    path('address/<int:pk>/', AddressView.as_view(), name='address-detail'),
    path('complete_order/', CompleteOrderView.as_view(), name='complete-order'),
    path('cancel/', CancelSeatBookingView.as_view(), name='cancel-seat-booking'),
]
