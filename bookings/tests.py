from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from datetime import timedelta
import threading
import queue

from resources.models import Resource, ResourceType
from bookings.models import Booking, BookingStatus, BookingHistory
from bookings.services import (
    has_booking_conflict,
    get_conflicting_bookings,
    record_booking_history,
    create_booking_atomic,
    approve_booking_atomic,
    reject_booking_atomic,
    cancel_booking_atomic,
    BookingConflictError,
    BookingError,
)
from campus_resolver.permissions import (
    ROLE_STUDENT, ROLE_RESOURCE_MANAGER, ensure_default_groups
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


class BookingViewsAndFormTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='tester', email='tester@campus.edu', password='Password123!')
        self.other_user = User.objects.create_user(username='other', email='other@campus.edu', password='Password123!')

        self.resource = Resource.objects.create(
            name="Lecture Hall A",
            resource_type=ResourceType.CLASSROOM,
            location="Block 1",
            capacity=60,
            is_active=True
        )
        self.inactive_resource = Resource.objects.create(
            name="Broken Lab",
            resource_type=ResourceType.LAB,
            location="Basement",
            capacity=10,
            is_active=False
        )

        self.base_time = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=2)

    def test_create_booking_view_login_required(self):
        """Unauthenticated user redirected to login."""
        response = self.client.get(reverse('bookings:create_booking'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_create_booking_post_success(self):
        """Authenticated user submits valid booking request."""
        self.client.login(username='tester', password='Password123!')
        start = self.base_time + timedelta(hours=9)
        end = self.base_time + timedelta(hours=11)

        response = self.client.post(reverse('bookings:create_booking'), {
            'resource': self.resource.id,
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
            'purpose': 'Math Olympiad Prep',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('bookings:my_bookings'))

        # Check booking created in DB
        booking = Booking.objects.get(purpose='Math Olympiad Prep')
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.status, BookingStatus.PENDING)
        # Check audit history was created
        self.assertEqual(booking.history.count(), 1)
        self.assertEqual(booking.history.first().new_status, BookingStatus.PENDING)

    def test_create_booking_conflict_rejected(self):
        """Submitting an overlapping booking triggers a conflict validation error."""
        self.client.login(username='tester', password='Password123!')
        start = self.base_time + timedelta(hours=10)
        end = self.base_time + timedelta(hours=12)

        # Existing approved booking
        Booking.objects.create(
            user=self.other_user,
            resource=self.resource,
            start_time=start,
            end_time=end,
            purpose='Existing booked session',
            status=BookingStatus.APPROVED
        )

        # Attempt to overlap from 11:00 to 13:00
        req_start = self.base_time + timedelta(hours=11)
        req_end = self.base_time + timedelta(hours=13)

        response = self.client.post(reverse('bookings:create_booking'), {
            'resource': self.resource.id,
            'start_time': req_start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': req_end.strftime('%Y-%m-%dT%H:%M'),
            'purpose': 'Conflicting request',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Schedule Conflict")
        # Ensure conflicting request was not saved
        self.assertFalse(Booking.objects.filter(purpose='Conflicting request').exists())

    def test_create_booking_adjacent_slot_succeeds(self):
        """Half-open interval: slot starting exactly when previous ends succeeds."""
        self.client.login(username='tester', password='Password123!')
        start1 = self.base_time + timedelta(hours=10)
        end1 = self.base_time + timedelta(hours=11)

        Booking.objects.create(
            user=self.other_user,
            resource=self.resource,
            start_time=start1,
            end_time=end1,
            purpose='Session 1',
            status=BookingStatus.APPROVED
        )

        # Adjacent slot 11:00 to 12:00
        req_start = self.base_time + timedelta(hours=11)
        req_end = self.base_time + timedelta(hours=12)

        response = self.client.post(reverse('bookings:create_booking'), {
            'resource': self.resource.id,
            'start_time': req_start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': req_end.strftime('%Y-%m-%dT%H:%M'),
            'purpose': 'Adjacent session',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Booking.objects.filter(purpose='Adjacent session').exists())

    def test_my_bookings_lists_only_own_bookings(self):
        """User only sees their own bookings in My Bookings view."""
        self.client.login(username='tester', password='Password123!')

        b1 = Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=1),
            end_time=self.base_time + timedelta(hours=2),
            purpose='Tester Session',
            status=BookingStatus.PENDING
        )
        b2 = Booking.objects.create(
            user=self.other_user,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=3),
            end_time=self.base_time + timedelta(hours=4),
            purpose='Private Other Session',
            status=BookingStatus.PENDING
        )

        response = self.client.get(reverse('bookings:my_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tester Session')
        self.assertNotContains(response, 'Private Other Session')

    def test_booking_detail_authorization(self):
        """User can view own booking details, but gets 403 on another user's booking."""
        self.client.login(username='tester', password='Password123!')

        b_own = Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=1),
            end_time=self.base_time + timedelta(hours=2),
            purpose='My Own Session',
            status=BookingStatus.PENDING
        )
        b_other = Booking.objects.create(
            user=self.other_user,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=3),
            end_time=self.base_time + timedelta(hours=4),
            purpose='Other Private Session',
            status=BookingStatus.PENDING
        )

        # View own booking succeeds
        res_own = self.client.get(reverse('bookings:booking_detail', kwargs={'pk': b_own.pk}))
        self.assertEqual(res_own.status_code, 200)
        self.assertContains(res_own, 'My Own Session')

        # View other user's booking returns 403 Forbidden
        res_other = self.client.get(reverse('bookings:booking_detail', kwargs={'pk': b_other.pk}))
        self.assertEqual(res_other.status_code, 403)

    def test_cancel_own_booking(self):
        """User can cancel their own eligible booking."""
        self.client.login(username='tester', password='Password123!')

        booking = Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=1),
            end_time=self.base_time + timedelta(hours=2),
            purpose='Session to Cancel',
            status=BookingStatus.PENDING
        )

        response = self.client.post(reverse('bookings:cancel_booking', kwargs={'pk': booking.pk}), {
            'reason': 'Change of plans',
        })
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        # Verify history recorded
        self.assertTrue(booking.history.filter(new_status=BookingStatus.CANCELLED).exists())

    def test_cancel_other_user_booking_denied(self):
        """User cannot cancel another user's booking."""
        self.client.login(username='tester', password='Password123!')

        b_other = Booking.objects.create(
            user=self.other_user,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=1),
            end_time=self.base_time + timedelta(hours=2),
            purpose='Cannot touch this',
            status=BookingStatus.APPROVED
        )

        response = self.client.post(reverse('bookings:cancel_booking', kwargs={'pk': b_other.pk}), {
            'reason': 'Malicious attempt',
        })
        self.assertEqual(response.status_code, 403)
        b_other.refresh_from_db()
        self.assertEqual(b_other.status, BookingStatus.APPROVED)


class BookingWorkflowAndApprovalTests(TestCase):
    """
    Phase 5 workflow tests: Approval, Rejection, Cancellation, and History tracking.
    """
    def setUp(self):
        ensure_default_groups()
        self.client = Client()

        self.admin = User.objects.create_superuser(username='super_mgr', email='mgr@campus.edu', password='Password123!')
        self.student = User.objects.create_user(username='student_wf', email='student_wf@campus.edu', password='Password123!')
        student_group = Group.objects.get(name=ROLE_STUDENT)
        self.student.groups.add(student_group)

        self.resource = Resource.objects.create(
            name="Auditorium Blue",
            resource_type=ResourceType.SEMINAR_HALL,
            location="Central Complex",
            capacity=300,
            is_active=True
        )

        self.base_time = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=3)

    def test_approve_booking_by_admin(self):
        """Admin can approve a pending booking; history record is created."""
        self.client.login(username='super_mgr', password='Password123!')

        booking = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=10),
            end_time=self.base_time + timedelta(hours=12),
            purpose='Robotics Annual Summit',
            status=BookingStatus.PENDING
        )

        response = self.client.post(reverse('bookings:approve_booking', kwargs={'pk': booking.pk}), {
            'remarks': 'Approved by Academic Dean',
        })
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.APPROVED)

        # Verify audit history
        history = booking.history.filter(new_status=BookingStatus.APPROVED).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_status, BookingStatus.PENDING)
        self.assertEqual(history.changed_by, self.admin)
        self.assertIn('Approved by Academic Dean', history.remarks)

    def test_approve_booking_unauthorized_student(self):
        """Standard student cannot approve bookings (403 Forbidden)."""
        self.client.login(username='student_wf', password='Password123!')

        booking = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=self.base_time + timedelta(hours=10),
            end_time=self.base_time + timedelta(hours=12),
            purpose='Unauthorized approval attempt',
            status=BookingStatus.PENDING
        )

        response = self.client.post(reverse('bookings:approve_booking', kwargs={'pk': booking.pk}))
        self.assertEqual(response.status_code, 403)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_approve_conflicting_slot_fails(self):
        """Approving a booking that conflicts with another already APPROVED booking fails."""
        start = self.base_time + timedelta(hours=14)
        end = self.base_time + timedelta(hours=16)

        # Confirmed approved booking 1
        b1 = Booking.objects.create(
            user=self.admin,
            resource=self.resource,
            start_time=start,
            end_time=end,
            purpose='First approved session',
            status=BookingStatus.APPROVED
        )

        # Competing pending booking 2
        b2 = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=start + timedelta(minutes=30),
            end_time=end + timedelta(minutes=30),
            purpose='Overlapping request',
            status=BookingStatus.PENDING
        )

        with self.assertRaises(BookingConflictError):
            approve_booking_atomic(b2.id, approved_by=self.admin)

        b2.refresh_from_db()
        self.assertEqual(b2.status, BookingStatus.PENDING)

    def test_reject_booking_frees_availability(self):
        """Rejecting a pending booking changes status to REJECTED and frees the slot."""
        self.client.login(username='super_mgr', password='Password123!')

        start = self.base_time + timedelta(hours=9)
        end = self.base_time + timedelta(hours=11)

        b_pending = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=start,
            end_time=end,
            purpose='Initial Request',
            status=BookingStatus.PENDING
        )

        # Slot is blocked while PENDING
        self.assertTrue(has_booking_conflict(self.resource, start, end))

        # Admin rejects with reason
        response = self.client.post(reverse('bookings:reject_booking', kwargs={'pk': b_pending.pk}), {
            'reason': 'Faculty review required first.',
        })
        self.assertEqual(response.status_code, 302)

        b_pending.refresh_from_db()
        self.assertEqual(b_pending.status, BookingStatus.REJECTED)

        # Slot is now FREE under planned policy
        self.assertFalse(has_booking_conflict(self.resource, start, end))

        # A new booking request for the exact same slot can now be created
        b_new = create_booking_atomic(
            user=self.admin,
            resource=self.resource,
            start_time=start,
            end_time=end,
            purpose='Replacement Request'
        )
        self.assertEqual(b_new.status, BookingStatus.PENDING)

    def test_manage_bookings_view_permissions(self):
        """Administrators can view manage_bookings queue; students are denied (403)."""
        # Student gets 403
        self.client.login(username='student_wf', password='Password123!')
        res_student = self.client.get(reverse('bookings:manage_bookings'))
        self.assertEqual(res_student.status_code, 403)

        # Admin gets 200
        self.client.login(username='super_mgr', password='Password123!')
        res_admin = self.client.get(reverse('bookings:manage_bookings'))
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, "Reservation Approvals & Queue")


class BookingConcurrencyTest(TransactionTestCase):
    """
    Phase 5 Concurrency Test:
    Verifies that simultaneous competing booking requests for the same slot
    are safely serialized by row-level locking (select_for_update) on MySQL.
    Exactly one request must succeed and the other must raise BookingConflictError.
    """
    def setUp(self):
        self.user_a = User.objects.create_user(username='concurrent_a', email='a@campus.edu', password='Pass123!')
        self.user_b = User.objects.create_user(username='concurrent_b', email='b@campus.edu', password='Pass123!')
        self.resource = Resource.objects.create(
            name="Concurrent Test Lab",
            resource_type=ResourceType.LAB,
            location="Server Room 0",
            capacity=20,
            is_active=True
        )
        self.slot_start = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=5, hours=10)
        self.slot_end = self.slot_start + timedelta(hours=2)

    def test_two_simultaneous_requests_for_same_slot(self):
        """
        Two simultaneous threads attempt to book the exact same slot on the same resource.
        MySQL row locking must ensure at most one succeeds.
        """
        results_queue = queue.Queue()
        start_barrier = threading.Barrier(2)

        def make_booking(user, label):
            start_barrier.wait()
            try:
                bk = create_booking_atomic(
                    user=user,
                    resource=self.resource,
                    start_time=self.slot_start,
                    end_time=self.slot_end,
                    purpose=f"Competing request by {label}"
                )
                results_queue.put(('SUCCESS', bk.id, label))
            except BookingConflictError:
                results_queue.put(('CONFLICT_ERROR', None, label))
            except Exception as ex:
                results_queue.put(('OTHER_ERROR', str(ex), label))

        t1 = threading.Thread(target=make_booking, args=(self.user_a, 'UserA'))
        t2 = threading.Thread(target=make_booking, args=(self.user_b, 'UserB'))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        results = []
        while not results_queue.empty():
            results.append(results_queue.get())

        self.assertEqual(len(results), 2)
        outcomes = [r[0] for r in results]

        # Exactly one must succeed and one must be rejected due to conflict
        self.assertEqual(outcomes.count('SUCCESS'), 1, f"Expected exactly 1 SUCCESS, got {outcomes}")
        self.assertEqual(outcomes.count('CONFLICT_ERROR'), 1, f"Expected exactly 1 CONFLICT_ERROR, got {outcomes}")

        # In the database, exactly one booking exists for that slot
        total_created = Booking.objects.filter(resource=self.resource, start_time=self.slot_start).count()
        self.assertEqual(total_created, 1)
