from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from resources.models import Resource
from bookings.models import Booking, BookingStatus
from campus_resolver.permissions import is_admin_or_staff, is_resource_manager, get_user_role


@login_required
def dashboard_home(request):
    """
    Role-aware central dashboard view.
    Renders metrics, pending requests, and shortcuts customized to user permissions.
    """
    user = request.user
    role = get_user_role(user)
    is_admin = is_admin_or_staff(user)
    is_manager = is_resource_manager(user)

    context = {
        'user_role': role,
        'is_admin': is_admin,
        'is_manager': is_manager,
    }

    if is_admin or is_manager:
        # Administrative / Resource Manager dashboard metrics
        total_resources = Resource.objects.count()
        active_resources = Resource.objects.filter(is_active=True).count()
        pending_bookings = Booking.objects.filter(status=BookingStatus.PENDING).count()
        approved_bookings = Booking.objects.filter(status=BookingStatus.APPROVED).count()
        recent_pending_requests = Booking.objects.filter(
            status=BookingStatus.PENDING
        ).select_related('resource', 'user').order_by('-created_at')[:5]

        context.update({
            'total_resources': total_resources,
            'active_resources': active_resources,
            'pending_bookings': pending_bookings,
            'approved_bookings': approved_bookings,
            'recent_pending_requests': recent_pending_requests,
        })
    else:
        # Student / Faculty personal reservation dashboard metrics
        user_bookings = Booking.objects.filter(user=user)
        total_user_bookings = user_bookings.count()
        pending_user_bookings = user_bookings.filter(status=BookingStatus.PENDING).count()
        approved_user_bookings = user_bookings.filter(status=BookingStatus.APPROVED).count()
        recent_user_bookings = user_bookings.select_related('resource').order_by('-created_at')[:5]

        context.update({
            'total_user_bookings': total_user_bookings,
            'pending_user_bookings': pending_user_bookings,
            'approved_user_bookings': approved_user_bookings,
            'recent_user_bookings': recent_user_bookings,
        })

    return render(request, 'dashboard/dashboard.html', context)
