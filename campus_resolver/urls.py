"""
URL Configuration for Campus Resource Conflict Resolver.
Phase 3: Authentication, Permissions, and Dashboard Routing.
"""

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from . import views


def home_redirect(request):
    """Root URL redirects to dashboard if authenticated, or login."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


urlpatterns = [
    # Administration
    path('admin/', admin.site.urls),

    # Authentication
    path('register/', views.register_view, name='register'),
    path('login/', views.CampusLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password_change/', views.CampusPasswordChangeView.as_view(), name='password_change'),
    path('password_change/done/', views.CampusPasswordChangeDoneView.as_view(), name='password_change_done'),

    # Dashboard & Root
    path('dashboard/', include('dashboard.urls')),
    path('', home_redirect, name='home'),
]
