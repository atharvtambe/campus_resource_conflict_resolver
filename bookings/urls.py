from django.urls import path
from . import views

app_name = 'bookings'

urlpatterns = [
    # User reservation flows
    path('book/', views.create_booking, name='create_booking'),
    path('book/<int:resource_id>/', views.create_booking, name='create_booking_for_resource'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('<int:pk>/', views.booking_detail, name='booking_detail'),
    path('<int:pk>/cancel/', views.cancel_booking, name='cancel_booking'),

    # Phase 5: Approval & Management workflows
    path('manage/', views.manage_bookings, name='manage_bookings'),
    path('<int:pk>/approve/', views.approve_booking, name='approve_booking'),
    path('<int:pk>/reject/', views.reject_booking, name='reject_booking'),
]
