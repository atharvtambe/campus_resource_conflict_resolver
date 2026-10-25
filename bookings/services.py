from django.db import transaction
from django.utils import timezone
from .models import Booking, BookingStatus, BookingHistory
from resources.models import Resource, ResourceBlock


class BookingError(Exception):
    """Base exception for booking workflow failures."""
    pass


class BookingConflictError(BookingError):
    """Raised when a requested reservation overlaps with an existing reservation or maintenance window."""
    pass


class InactiveResourceError(BookingError):
    """Raised when attempting to book a deactivated resource."""
    pass


class InvalidTimeRangeError(BookingError):
    """Raised when start_time >= end_time or duration is invalid."""
    pass


def get_conflicting_bookings(resource, start_time, end_time, exclude_booking_id=None):
    """
    Finds existing bookings that conflict with the requested half-open interval [start_time, end_time).
    A conflict exists when:
      existing.start_time < requested_end AND existing.end_time > requested_start
    Both PENDING and APPROVED bookings are considered blocking according to project policy.
    """
    conflicts = Booking.objects.filter(
        resource=resource,
        start_time__lt=end_time,
        end_time__gt=start_time,
        status__in=[BookingStatus.PENDING, BookingStatus.APPROVED]
    )
    if exclude_booking_id:
        conflicts = conflicts.exclude(id=exclude_booking_id)
    return conflicts


def get_conflicting_maintenance_blocks(resource, start_time, end_time):
    """
    Finds maintenance blocks that overlap with the requested interval.
    """
    return ResourceBlock.objects.filter(
        resource=resource,
        start_time__lt=end_time,
        end_time__gt=start_time
    )


def has_booking_conflict(resource, start_time, end_time, exclude_booking_id=None):
    """
    Returns True if either a blocking reservation or maintenance window overlaps with the requested slot.
    """
    booking_conflicts = get_conflicting_bookings(resource, start_time, end_time, exclude_booking_id)
    if booking_conflicts.exists():
        return True
    
    maintenance_conflicts = get_conflicting_maintenance_blocks(resource, start_time, end_time)
    if maintenance_conflicts.exists():
        return True

    return False


@transaction.atomic
def record_booking_history(booking, changed_by, old_status, new_status, remarks=""):
    """
    Audit logger helper to create a history record when a booking status changes.
    """
    return BookingHistory.objects.create(
        booking=booking,
        changed_by=changed_by,
        old_status=old_status,
        new_status=new_status,
        remarks=remarks
    )


@transaction.atomic
def create_booking_atomic(user, resource, start_time, end_time, purpose, remarks="Booking request submitted."):
    """
    Concurrency-safe booking creation using row-level locking (select_for_update).
    Locks the resource row during the transaction to serialize simultaneous requests for the same resource,
    preventing race conditions / duplicate bookings on MySQL.
    """
    if start_time >= end_time:
        raise InvalidTimeRangeError("Booking start time must be strictly earlier than end time.")

    # Acquire pessimistic row-level lock on the resource
    locked_resource = Resource.objects.select_for_update().get(id=resource.id)

    if not locked_resource.is_active:
        raise InactiveResourceError(f"Resource '{locked_resource.name}' is currently inactive.")

    # Verify no conflicting booking exists in the locked transaction
    if has_booking_conflict(locked_resource, start_time, end_time):
        raise BookingConflictError(
            f"Schedule Conflict: Resource '{locked_resource.name}' is unavailable during this time interval."
        )

    booking = Booking.objects.create(
        user=user,
        resource=locked_resource,
        start_time=start_time,
        end_time=end_time,
        purpose=purpose,
        status=BookingStatus.PENDING
    )

    record_booking_history(
        booking=booking,
        changed_by=user,
        old_status="",
        new_status=BookingStatus.PENDING,
        remarks=remarks
    )

    return booking


@transaction.atomic
def approve_booking_atomic(booking_id, approved_by, remarks="Approved by administrator."):
    """
    Concurrency-safe booking approval workflow.
    Locks both the booking and its resource to guarantee no conflicting approved booking
    was committed simultaneously.
    """
    booking = Booking.objects.select_for_update().select_related('resource').get(id=booking_id)
    Resource.objects.select_for_update().get(id=booking.resource_id)

    if booking.status == BookingStatus.APPROVED:
        return booking

    if booking.status in [BookingStatus.CANCELLED, BookingStatus.REJECTED]:
        raise BookingError(f"Cannot approve a {booking.get_status_display().lower()} booking.")

    # Check if another booking has already been APPROVED for an overlapping slot
    approved_conflicts = Booking.objects.filter(
        resource=booking.resource,
        start_time__lt=booking.end_time,
        end_time__gt=booking.start_time,
        status=BookingStatus.APPROVED
    ).exclude(id=booking.id)

    if approved_conflicts.exists():
        raise BookingConflictError("Another reservation has already been approved for this overlapping time slot.")

    # Check maintenance blocks
    maintenance_conflicts = get_conflicting_maintenance_blocks(booking.resource, booking.start_time, booking.end_time)
    if maintenance_conflicts.exists():
        raise BookingConflictError("Resource is scheduled for maintenance during this time slot.")

    old_status = booking.status
    booking.status = BookingStatus.APPROVED
    booking.save()

    record_booking_history(
        booking=booking,
        changed_by=approved_by,
        old_status=old_status,
        new_status=BookingStatus.APPROVED,
        remarks=remarks
    )

    return booking


@transaction.atomic
def reject_booking_atomic(booking_id, rejected_by, reason="Rejected by administrator."):
    """
    Rejects a pending booking and records the reason in audit history.
    Freed slots automatically become available to other users.
    """
    booking = Booking.objects.select_for_update().get(id=booking_id)

    if booking.status == BookingStatus.REJECTED:
        return booking

    old_status = booking.status
    booking.status = BookingStatus.REJECTED
    booking.save()

    record_booking_history(
        booking=booking,
        changed_by=rejected_by,
        old_status=old_status,
        new_status=BookingStatus.REJECTED,
        remarks=reason
    )

    return booking


@transaction.atomic
def cancel_booking_atomic(booking_id, cancelled_by, reason=""):
    """
    Cancels an eligible pending or approved booking and records the cancellation in audit history.
    """
    booking = Booking.objects.select_for_update().get(id=booking_id)

    if booking.status in [BookingStatus.CANCELLED, BookingStatus.REJECTED]:
        return booking

    old_status = booking.status
    booking.status = BookingStatus.CANCELLED
    booking.save()

    remarks = f"Cancelled by {cancelled_by.username}."
    if reason:
        remarks += f" Reason: {reason}"

    record_booking_history(
        booking=booking,
        changed_by=cancelled_by,
        old_status=old_status,
        new_status=BookingStatus.CANCELLED,
        remarks=remarks
    )

    return booking
