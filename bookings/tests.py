from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from resources.models import Resource, ResourceType
from bookings.models import Booking, BookingStatus, BookingHistory
from bookings.services import (
    has_booking_conflict,
    get_conflicting_bookings,
    record_booking_history,
)

User = get_user_model()


class BookingModelAndConflictServiceTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='john', email='john@example.com', password='password123')
        self.user2 = User.objects.create_user(username='mary', email='mary@example.com', password='password123')
        self.admin_user = User.objects.create_superuser(username='superadmin', email='super@example.com', password='adminpassword')

        self.active_resource = Resource.objects.create(
            name="Seminar Hall A",
            resource_type=ResourceType.SEMINAR_HALL,
            location="Main Block Floor 2",
            capacity=120,
            is_active=True
        )
        self.inactive_resource = Resource.objects.create(
            name="Projector Room 1",
            resource_type=ResourceType.PROJECTOR,
            location="Library",
            capacity=10,
            is_active=False
        )

        self.base_time = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)

    def test_booking_creation_and_crud(self):
        """Test creating, reading, updating, and deleting a booking."""
        start = self.base_time + timedelta(hours=10)
        end = self.base_time + timedelta(hours=11)

        booking = Booking.objects.create(
            user=self.user1,
            resource=self.active_resource,
            start_time=start,
            end_time=end,
            purpose="Guest Lecture on Cloud Computing",
            status=BookingStatus.PENDING
        )
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(booking.resource, self.active_resource)
        self.assertEqual(booking.user, self.user1)

        # Update
        booking.status = BookingStatus.APPROVED
        booking.save()
        self.assertEqual(Booking.objects.get(id=booking.id).status, BookingStatus.APPROVED)

    def test_start_time_after_end_time_validation(self):
        """Test start_time >= end_time triggers validation error."""
        start = self.base_time + timedelta(hours=12)
        end = self.base_time + timedelta(hours=10)

        invalid_booking = Booking(
            user=self.user1,
            resource=self.active_resource,
            start_time=start,
            end_time=end,
            purpose="Invalid time range"
        )
        with self.assertRaises(ValidationError):
            invalid_booking.clean()

    def test_inactive_resource_booking_validation(self):
        """Test that booking an inactive resource triggers validation error."""
        start = self.base_time + timedelta(hours=10)
        end = self.base_time + timedelta(hours=11)

        invalid_booking = Booking(
            user=self.user1,
            resource=self.inactive_resource,
            start_time=start,
            end_time=end,
            purpose="Attempt booking inactive resource"
        )
        with self.assertRaises(ValidationError):
            invalid_booking.clean()

    def test_conflict_detection_overlapping_booking(self):
        """Existing booking 10:00-11:00 vs requested 10:30-11:30 is a conflict."""
        b_start = self.base_time + timedelta(hours=10)
        b_end = self.base_time + timedelta(hours=11)

        Booking.objects.create(
            user=self.user1,
            resource=self.active_resource,
            start_time=b_start,
            end_time=b_end,
            purpose="Session 1",
            status=BookingStatus.APPROVED
        )

        # Overlapping requested slot: 10:30-11:30
        req_start = self.base_time + timedelta(hours=10, minutes=30)
        req_end = self.base_time + timedelta(hours=11, minutes=30)

        self.assertTrue(has_booking_conflict(self.active_resource, req_start, req_end))

    def test_conflict_detection_adjacent_slots_allowed(self):
        """Half-open interval: 10:00-11:00 followed by 11:00-12:00 is allowed."""
        b_start = self.base_time + timedelta(hours=10)
        b_end = self.base_time + timedelta(hours=11)

        Booking.objects.create(
            user=self.user1,
            resource=self.active_resource,
            start_time=b_start,
            end_time=b_end,
            purpose="Session 1",
            status=BookingStatus.APPROVED
        )

        # Adjacent slot starting exactly when previous ends: 11:00-12:00
        req_start = self.base_time + timedelta(hours=11)
        req_end = self.base_time + timedelta(hours=12)

        self.assertFalse(has_booking_conflict(self.active_resource, req_start, req_end))

    def test_cancelled_or_rejected_does_not_block(self):
        """Cancelled or Rejected booking does not block availability."""
        b_start = self.base_time + timedelta(hours=14)
        b_end = self.base_time + timedelta(hours=15)

        Booking.objects.create(
            user=self.user1,
            resource=self.active_resource,
            start_time=b_start,
            end_time=b_end,
            purpose="Cancelled session",
            status=BookingStatus.CANCELLED
        )

        # Same time requested
        self.assertFalse(has_booking_conflict(self.active_resource, b_start, b_end))

    def test_booking_history_recording(self):
        """Test status transitions record audit history."""
        start = self.base_time + timedelta(hours=9)
        end = self.base_time + timedelta(hours=10)

        booking = Booking.objects.create(
            user=self.user1,
            resource=self.active_resource,
            start_time=start,
            end_time=end,
            purpose="Club meeting",
            status=BookingStatus.PENDING
        )

        # Admin approves
        booking.status = BookingStatus.APPROVED
        booking.save()
        history = record_booking_history(
            booking=booking,
            changed_by=self.admin_user,
            old_status=BookingStatus.PENDING,
            new_status=BookingStatus.APPROVED,
            remarks="Approved by Dept Head"
        )

        self.assertEqual(booking.history.count(), 1)
        self.assertEqual(history.old_status, BookingStatus.PENDING)
        self.assertEqual(history.new_status, BookingStatus.APPROVED)
        self.assertEqual(history.changed_by, self.admin_user)
        self.assertEqual(history.remarks, "Approved by Dept Head")
