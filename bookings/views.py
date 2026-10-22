from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.utils import timezone

from .models import Booking, BookingStatus, BookingHistory
from .forms import BookingForm
from .services import record_booking_history
from resources.models import Resource
from campus_resolver.permissions import can_view_booking, can_cancel_booking


@login_required
def create_booking(request, resource_id=None):
    """
    Booking creation view allowing authenticated students/faculty to reserve resources.
    Validates half-open intervals and checks conflicts against existing bookings/maintenance.
    """
    initial_data = {}
    selected_resource = None

    if resource_id:
        selected_resource = get_object_or_404(Resource, pk=resource_id)
        if not selected_resource.is_active:
            messages.warning(request, f"Resource '{selected_resource.name}' is currently inactive.")
        initial_data['resource'] = selected_resource

    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.user = request.user
            booking.status = BookingStatus.PENDING
            booking.save()

            # Record audit history
            record_booking_history(
                booking=booking,
                changed_by=request.user,
                old_status="",
                new_status=BookingStatus.PENDING,
                remarks="Booking request submitted."
            )

            messages.success(
                request,
                f"Booking request for '{booking.resource.name}' submitted successfully! Awaiting administrator approval."
            )
            return redirect('bookings:my_bookings')
        else:
            messages.error(request, "Please correct the errors indicated below.")
    else:
        form = BookingForm(initial=initial_data)

    return render(request, 'bookings/booking_form.html', {
        'form': form,
        'selected_resource': selected_resource,
    })


@login_required
def my_bookings(request):
    """
    Displays personal reservations of the authenticated user with status filtering and cancellation actions.
    """
    status_filter = request.GET.get('status', '').strip().upper()
    user_bookings = Booking.objects.filter(user=request.user).select_related('resource').order_by('-created_at')

    if status_filter in [BookingStatus.PENDING, BookingStatus.APPROVED, BookingStatus.CANCELLED, BookingStatus.REJECTED]:
        user_bookings = user_bookings.filter(status=status_filter)

    paginator = Paginator(user_bookings, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'bookings/my_bookings.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'statuses': BookingStatus.choices,
        'total_count': user_bookings.count(),
    })


@login_required
def booking_detail(request, pk):
    """
    Shows full booking details, time intervals, purpose, and status change audit trail.
    Enforces object-level authorization: users can only view their own bookings,
    while managers and admins can inspect any booking.
    """
    booking = get_object_or_404(Booking.objects.select_related('resource', 'user'), pk=pk)

    if not can_view_booking(request.user, booking):
        raise PermissionDenied("You do not have permission to view this reservation.")

    history_records = booking.history.select_related('changed_by').order_by('-changed_at')
    can_cancel = can_cancel_booking(request.user, booking) and booking.status in [BookingStatus.PENDING, BookingStatus.APPROVED]

    return render(request, 'bookings/booking_detail.html', {
        'booking': booking,
        'history_records': history_records,
        'can_cancel': can_cancel,
    })


@login_required
def cancel_booking(request, pk):
    """
    Cancels an eligible pending or approved booking.
    """
    booking = get_object_or_404(Booking, pk=pk)

    if not can_cancel_booking(request.user, booking):
        raise PermissionDenied("You do not have permission to cancel this reservation.")

    if booking.status in [BookingStatus.CANCELLED, BookingStatus.REJECTED]:
        messages.warning(request, f"Booking #{booking.id} is already {booking.get_status_display().lower()}.")
        return redirect('bookings:my_bookings')

    if request.method == 'POST':
        old_status = booking.status
        booking.status = BookingStatus.CANCELLED
        booking.save()

        cancellation_reason = request.POST.get('reason', '').strip()
        remarks = f"Cancelled by {request.user.username}."
        if cancellation_reason:
            remarks += f" Reason: {cancellation_reason}"

        record_booking_history(
            booking=booking,
            changed_by=request.user,
            old_status=old_status,
            new_status=BookingStatus.CANCELLED,
            remarks=remarks
        )

        messages.success(request, f"Booking #{booking.id} for '{booking.resource.name}' has been cancelled.")
        return redirect('bookings:my_bookings')

    return render(request, 'bookings/booking_confirm_cancel.html', {
        'booking': booking,
    })
