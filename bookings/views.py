from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import Booking, BookingStatus, BookingHistory
from .forms import BookingForm
from .services import (
    create_booking_atomic,
    approve_booking_atomic,
    reject_booking_atomic,
    cancel_booking_atomic,
    BookingConflictError,
    BookingError,
    record_booking_history,
)
from resources.models import Resource
from campus_resolver.permissions import (
    can_view_booking,
    can_cancel_booking,
    can_manage_booking,
    is_admin_or_staff,
    is_resource_manager,
)


@login_required
def create_booking(request, resource_id=None):
    """
    Booking creation view allowing authenticated students/faculty to reserve resources.
    Uses concurrency-safe atomic transactions and row-level locking to prevent race conditions.
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
            resource = form.cleaned_data['resource']
            start_time = form.cleaned_data['start_time']
            end_time = form.cleaned_data['end_time']
            purpose = form.cleaned_data['purpose']

            try:
                booking = create_booking_atomic(
                    user=request.user,
                    resource=resource,
                    start_time=start_time,
                    end_time=end_time,
                    purpose=purpose,
                    remarks="Booking request submitted."
                )

                messages.success(
                    request,
                    f"Booking request for '{booking.resource.name}' submitted successfully! Awaiting administrator approval."
                )
                return redirect('bookings:my_bookings')
            except BookingConflictError as e:
                form.add_error(None, str(e))
                messages.error(request, str(e))
            except BookingError as e:
                form.add_error(None, str(e))
                messages.error(request, str(e))
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
    while managers and admins can inspect any booking and take approval actions.
    """
    booking = get_object_or_404(Booking.objects.select_related('resource', 'user'), pk=pk)

    if not can_view_booking(request.user, booking):
        raise PermissionDenied("You do not have permission to view this reservation.")

    history_records = booking.history.select_related('changed_by').order_by('-changed_at')
    can_cancel = can_cancel_booking(request.user, booking) and booking.status in [BookingStatus.PENDING, BookingStatus.APPROVED]
    can_manage = can_manage_booking(request.user, booking)

    return render(request, 'bookings/booking_detail.html', {
        'booking': booking,
        'history_records': history_records,
        'can_cancel': can_cancel,
        'can_manage': can_manage,
    })


@login_required
def approve_booking(request, pk):
    """
    Approval workflow: Administrators and Resource Managers approve a pending booking.
    Concurrency-safe: checks for conflicting approved slots in a locked transaction.
    """
    booking = get_object_or_404(Booking, pk=pk)

    if not can_manage_booking(request.user, booking):
        raise PermissionDenied("You do not have administrative privileges to approve booking requests.")

    if request.method == 'POST':
        remarks = request.POST.get('remarks', '').strip()
        if not remarks:
            remarks = f"Approved by {request.user.username}."
        else:
            remarks = f"Approved by {request.user.username}: {remarks}"

        try:
            approve_booking_atomic(
                booking_id=booking.id,
                approved_by=request.user,
                remarks=remarks
            )
            messages.success(request, f"Booking #{booking.id} for '{booking.resource.name}' has been APPROVED.")
        except BookingConflictError as e:
            messages.error(request, f"Approval Conflict: {e}")
        except BookingError as e:
            messages.error(request, str(e))

    next_url = request.POST.get('next') or request.GET.get('next') or 'bookings:manage_bookings'
    return redirect(next_url)


@login_required
def reject_booking(request, pk):
    """
    Rejection workflow: Administrators and Resource Managers reject a booking with a reason.
    """
    booking = get_object_or_404(Booking, pk=pk)

    if not can_manage_booking(request.user, booking):
        raise PermissionDenied("You do not have administrative privileges to reject booking requests.")

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        remarks = f"Rejected by {request.user.username}."
        if reason:
            remarks += f" Reason: {reason}"

        try:
            reject_booking_atomic(
                booking_id=booking.id,
                rejected_by=request.user,
                reason=remarks
            )
            messages.info(request, f"Booking #{booking.id} has been REJECTED. The time slot is now available.")
        except BookingError as e:
            messages.error(request, str(e))

    next_url = request.POST.get('next') or request.GET.get('next') or 'bookings:manage_bookings'
    return redirect(next_url)


@login_required
def cancel_booking(request, pk):
    """
    Cancels an eligible pending or approved booking using atomic transaction and records history.
    """
    booking = get_object_or_404(Booking, pk=pk)

    if not can_cancel_booking(request.user, booking):
        raise PermissionDenied("You do not have permission to cancel this reservation.")

    if booking.status in [BookingStatus.CANCELLED, BookingStatus.REJECTED]:
        messages.warning(request, f"Booking #{booking.id} is already {booking.get_status_display().lower()}.")
        return redirect('bookings:my_bookings')

    if request.method == 'POST':
        cancellation_reason = request.POST.get('reason', '').strip()
        try:
            cancel_booking_atomic(
                booking_id=booking.id,
                cancelled_by=request.user,
                reason=cancellation_reason
            )
            messages.success(request, f"Booking #{booking.id} for '{booking.resource.name}' has been cancelled.")
        except BookingError as e:
            messages.error(request, str(e))

        return redirect('bookings:my_bookings')

    return render(request, 'bookings/booking_confirm_cancel.html', {
        'booking': booking,
    })


@login_required
def manage_bookings(request):
    """
    Central booking approvals workbench for administrators and resource managers.
    Enables searching, status filtering, and 1-click approvals and rejections.
    """
    if not is_resource_manager(request.user):
        raise PermissionDenied("You do not have administrative privileges to view all bookings.")

    status_filter = request.GET.get('status', '').strip().upper()
    resource_id = request.GET.get('resource', '').strip()
    q = request.GET.get('q', '').strip()

    bookings_query = Booking.objects.select_related('resource', 'user').order_by('-created_at')

    # Status filter
    if status_filter in [BookingStatus.PENDING, BookingStatus.APPROVED, BookingStatus.CANCELLED, BookingStatus.REJECTED]:
        bookings_query = bookings_query.filter(status=status_filter)

    # Resource filter
    if resource_id.isdigit():
        bookings_query = bookings_query.filter(resource_id=int(resource_id))

    # Search keyword
    if q:
        bookings_query = bookings_query.filter(
            Q(user__username__icontains=q) |
            Q(purpose__icontains=q) |
            Q(resource__name__icontains=q)
        )

    # Counts for dashboard pills
    pending_count = Booking.objects.filter(status=BookingStatus.PENDING).count()
    approved_count = Booking.objects.filter(status=BookingStatus.APPROVED).count()
    total_count = Booking.objects.count()

    paginator = Paginator(bookings_query, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    resources = Resource.objects.all().order_by('name')

    return render(request, 'bookings/manage_bookings.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'selected_resource': resource_id,
        'search_q': q,
        'resources': resources,
        'statuses': BookingStatus.choices,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'total_count': total_count,
    })
