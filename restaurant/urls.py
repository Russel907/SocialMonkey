from django.contrib import admin
from django.urls import path
from .views import RestaurantRegisterView, RestaurantLoginView, MenuCreateListView, TableCreateView, PaymentCreateView, TimingView, SeatsCreateView, SeatSlotView, GalleryView, PerformanceView, OfferView, DiningOfferView, TableConfigView, CreateServerView, ServerDetailView, TableOrderListView, SeatOrderListView, SeatBookingDetailView

urlpatterns = [
    path('signup/', RestaurantRegisterView.as_view(), name="restaurants"),
    path('restaurant/<int:pk>/', RestaurantRegisterView.as_view(), name='restaurant-update'),
    path('login/', RestaurantLoginView.as_view(), name='login'),
    path('menu/', MenuCreateListView.as_view(), name='menus'),
    path('menu/<int:pk>/', MenuCreateListView.as_view(), name='menu-edit'),
    path('table/', TableCreateView.as_view(), name='tables'),
    path('table/<int:pk>/', TableCreateView.as_view(), name='table-edit'),
    path('payment/', PaymentCreateView.as_view(), name='payments'),
    path('payment/<int:pk>/', PaymentCreateView.as_view(), name='payment-edit'),
    path('timing/', TimingView.as_view(), name='timings'),
    path('timing/<int:pk>/', TimingView.as_view(), name='timing-edit'),
    path('seats/', SeatsCreateView.as_view(), name='seats'),
    path('seats/<int:pk>/', SeatsCreateView.as_view(), name='seats-detail'),
    path('slot/', SeatSlotView.as_view(), name='seat-slot'),
    path('slot/<int:pk>/', SeatSlotView.as_view(), name='seat-slot-detail'),
    path('gallery/', GalleryView.as_view(), name='gallery'),
    path('gallery/<int:pk>/', GalleryView.as_view(), name='gallery-detail'),
    path('performance/', PerformanceView.as_view(), name='performance'),
    path('performance/<int:pk>/', PerformanceView.as_view(), name='performance-delete'),
    path('offer/', OfferView.as_view(), name='offer'),
    path('offer/<int:pk>/', OfferView.as_view(), name='offer-detail'),
    path('diningoffer/', DiningOfferView.as_view(), name='diningoffer'),
    path('diningoffer/<int:pk>/', DiningOfferView.as_view(), name='diningoffer-detail'),
    path('tableconfig/', TableConfigView.as_view(), name='tableconfig'),
    path('tableconfig/<int:pk>/', TableConfigView.as_view(), name='tableconfig-detail'),
    path('server/', CreateServerView.as_view(), name='create-server'),
    path('server/<int:pk>/', ServerDetailView.as_view(), name='server-detail'),
    path('table-orders/', TableOrderListView.as_view(), name='table-order-list'),
    path('seat-booking-list/', SeatOrderListView.as_view(), name='seat-booking-list'),
    path('seat-booking-list/<int:pk>/', SeatBookingDetailView.as_view(), name='seat-booking-list'),

    
]
