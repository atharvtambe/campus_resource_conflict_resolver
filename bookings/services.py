from django.db import transaction
from django.utils import timezone
from .models import Booking, BookingStatus, BookingHistory
from resources.models import ResourceBlock


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
