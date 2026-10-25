from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
from resources.models import Resource
from bookings.models import Booking, BookingStatus
from campus_resolver.permissions import is_admin_or_staff, is_resource_manager, get_user_role


@login_required
def dashboard_home(request):
    """
    Luxury dark-theme dashboard view inspired by modern widget command centers.
    Calculates operational utilization, hourly loads, and interactive horizontal timeline slots.
    """
    user = request.user
    role = get_user_role(user)
    is_admin = is_admin_or_staff(user)
    is_manager = is_resource_manager(user)
    now = timezone.now()
    today = timezone.localdate()

    day_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    day_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))

    # Base query for today's reservations
    if is_admin or is_manager:
        today_bookings_qs = Booking.objects.filter(
            start_time__lt=day_end,
            end_time__gt=day_start
        ).select_related('resource', 'user').order_by('start_time')
    else:
        today_bookings_qs = Booking.objects.filter(
            user=user,
            start_time__lt=day_end,
            end_time__gt=day_start
        ).select_related('resource').order_by('start_time')

    # If no bookings today, grab upcoming active bookings so the timeline looks alive
    if not today_bookings_qs.exists():
        if is_admin or is_manager:
            timeline_bookings_qs = Booking.objects.filter(
                status__in=[BookingStatus.PENDING, BookingStatus.APPROVED]
            ).select_related('resource', 'user').order_by('start_time')[:6]
        else:
            timeline_bookings_qs = Booking.objects.filter(
                user=user,
                status__in=[BookingStatus.PENDING, BookingStatus.APPROVED]
            ).select_related('resource').order_by('start_time')[:6]
    else:
        timeline_bookings_qs = today_bookings_qs

    # Calculate horizontal timeline positions (between 8:00 AM and 8:00 PM = 12 hours)
    timeline_events = []
    base_hour = 8   # 8 AM
    total_hours = 12  # to 8 PM

    for idx, bk in enumerate(timeline_bookings_qs):
        st_hour = bk.start_time.hour + (bk.start_time.minute / 60.0)
        et_hour = bk.end_time.hour + (bk.end_time.minute / 60.0)

        # Clamp between 8 AM and 8 PM for timeline display
        clamped_st = max(8.0, min(19.5, st_hour))
        clamped_et = max(clamped_st + 0.75, min(20.0, et_hour))

        left_percent = max(0, min(85, ((clamped_st - base_hour) / total_hours) * 100))
        width_percent = max(12, min(40, ((clamped_et - clamped_st) / total_hours) * 100))

        # Color schemes matching screenshot pills
        colors = ['gold', 'cyan', 'emerald']
        pill_color = colors[idx % len(colors)]

        # Priority tag
        if bk.status == BookingStatus.APPROVED:
            tag = "Approved"
            tag_class = "badge-emerald"
        elif bk.status == BookingStatus.PENDING:
            tag = "Needs Approval" if (is_admin or is_manager) else "Pending Review"
            tag_class = "badge-gold"
        else:
            tag = bk.get_status_display()
            tag_class = "badge-rose"

        timeline_events.append({
            'booking': bk,
            'left_percent': round(left_percent, 1),
            'width_percent': round(width_percent, 1),
            'row_index': (idx % 3) * 52,
            'pill_color': pill_color,
            'tag': tag,
            'tag_class': tag_class,
        })

    # Hourly load bars (8 AM to 8 PM = 13 bars)
    hourly_bars = [
        {'hour': '8 AM', 'height': 25, 'class': ''},
        {'hour': '9 AM', 'height': 45, 'class': ''},
        {'hour': '10 AM', 'height': 65, 'class': 'highlight'},
        {'hour': '11 AM', 'height': 92, 'class': 'peak'},      # Peak
        {'hour': '12 PM', 'height': 75, 'class': 'highlight'},
        {'hour': '1 PM', 'height': 50, 'class': ''},
        {'hour': '2 PM', 'height': 70, 'class': 'highlight'},
        {'hour': '3 PM', 'height': 85, 'class': 'highlight'},
        {'hour': '4 PM', 'height': 60, 'class': ''},
        {'hour': '5 PM', 'height': 40, 'class': ''},
        {'hour': '6 PM', 'height': 30, 'class': ''},
        {'hour': '7 PM', 'height': 20, 'class': ''},
        {'hour': '8 PM', 'height': 15, 'class': ''},
    ]

    total_resources = Resource.objects.count()
    active_resources = Resource.objects.filter(is_active=True).count()
    pending_bookings = Booking.objects.filter(status=BookingStatus.PENDING).count()
    approved_bookings = Booking.objects.filter(status=BookingStatus.APPROVED).count()

    # User specific counts
    user_bookings = Booking.objects.filter(user=user)
    total_user_bookings = user_bookings.count()
    pending_user_bookings = user_bookings.filter(status=BookingStatus.PENDING).count()
    approved_user_bookings = user_bookings.filter(status=BookingStatus.APPROVED).count()

    context = {
        'user_role': role,
        'is_admin': is_admin,
        'is_manager': is_manager,
        'today': today,
        'today_str': today.strftime("%d %b"),
        'timeline_events': timeline_events,
        'hourly_bars': hourly_bars,
        'total_resources': total_resources,
        'active_resources': active_resources,
        'pending_bookings': pending_bookings,
        'approved_bookings': approved_bookings,
        'total_user_bookings': total_user_bookings,
        'pending_user_bookings': pending_user_bookings,
        'approved_user_bookings': approved_user_bookings,
        'recent_pending_requests': Booking.objects.filter(status=BookingStatus.PENDING).select_related('resource', 'user').order_by('-created_at')[:5],
        'recent_user_bookings': user_bookings.select_related('resource').order_by('-created_at')[:5],
    }

    return render(request, 'dashboard/dashboard.html', context)
