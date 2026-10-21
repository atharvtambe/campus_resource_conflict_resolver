from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from campus_resolver.permissions import (
    ROLE_STUDENT, ROLE_FACULTY, ROLE_RESOURCE_MANAGER, ROLE_ADMIN,
    get_user_role, is_admin_or_staff, is_resource_manager,
    can_view_booking, can_cancel_booking, can_manage_booking,
    admin_or_staff_required, role_required, ensure_default_groups
)
from resources.models import Resource, ResourceType
from bookings.models import Booking, BookingStatus

User = get_user_model()


class AuthenticationAndRegistrationTest(TestCase):
    def setUp(self):
        ensure_default_groups()
        self.client = Client()

    def test_user_registration_success_student(self):
        """Test successful registration as a student with role group assignment."""
        response = self.client.post(reverse('register'), {
            'username': 'alice_student',
            'email': 'alice@campus.edu',
            'first_name': 'Alice',
            'last_name': 'Smith',
            'role': ROLE_STUDENT,
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

        # Verify user created in DB
        user = User.objects.get(username='alice_student')
        self.assertEqual(user.email, 'alice@campus.edu')
        self.assertTrue(user.groups.filter(name=ROLE_STUDENT).exists())
        self.assertEqual(get_user_role(user), ROLE_STUDENT)
        # Verify password is hashed, never plaintext
        self.assertNotEqual(user.password, 'StrongPassword123!')
        self.assertTrue(user.check_password('StrongPassword123!'))

    def test_user_registration_success_faculty(self):
        """Test successful registration as a faculty member."""
        response = self.client.post(reverse('register'), {
            'username': 'prof_bob',
            'email': 'bob@campus.edu',
            'first_name': 'Bob',
            'last_name': 'Brown',
            'role': ROLE_FACULTY,
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='prof_bob')
        self.assertTrue(user.groups.filter(name=ROLE_FACULTY).exists())
        self.assertEqual(get_user_role(user), ROLE_FACULTY)

    def test_registration_duplicate_username_error(self):
        """Test that duplicate usernames (case-insensitive) are rejected."""
        User.objects.create_user(username='ExistingUser', email='old@campus.edu', password='Password123!')
        response = self.client.post(reverse('register'), {
            'username': 'existinguser',
            'email': 'new@campus.edu',
            'role': ROLE_STUDENT,
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A user with that username already exists.")

    def test_registration_duplicate_email_error(self):
        """Test that duplicate emails are rejected."""
        User.objects.create_user(username='user1', email='same@campus.edu', password='Password123!')
        response = self.client.post(reverse('register'), {
            'username': 'user2',
            'email': 'same@campus.edu',
            'role': ROLE_STUDENT,
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email address already exists.")

    def test_registration_password_mismatch(self):
        """Test that mismatched passwords trigger validation error."""
        response = self.client.post(reverse('register'), {
            'username': 'charlie',
            'email': 'charlie@campus.edu',
            'role': ROLE_STUDENT,
            'password': 'PasswordOne123!',
            'confirm_password': 'PasswordTwo123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match.")


class LoginLogoutTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='david',
            email='david@campus.edu',
            password='SecretPassword123!'
        )

    def test_login_success(self):
        """Test login with valid credentials redirects to dashboard."""
        response = self.client.post(reverse('login'), {
            'username': 'david',
            'password': 'SecretPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_invalid_password(self):
        """Test login with invalid password fails with error message."""
        response = self.client.post(reverse('login'), {
            'username': 'david',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")

    def test_authenticated_user_redirected_from_login(self):
        """Test that an already logged-in user is redirected away from login."""
        self.client.login(username='david', password='SecretPassword123!')
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_logout(self):
        """Test logout clears session and redirects to login."""
        self.client.login(username='david', password='SecretPassword123!')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))


class AuthorizationAndPermissionsTest(TestCase):
    def setUp(self):
        ensure_default_groups()
        self.client = Client()

        # Regular student user
        self.student = User.objects.create_user(username='student1', email='s1@campus.edu', password='Pass123!')
        student_group = Group.objects.get(name=ROLE_STUDENT)
        self.student.groups.add(student_group)

        # Regular faculty user
        self.faculty = User.objects.create_user(username='faculty1', email='f1@campus.edu', password='Pass123!')
        faculty_group = Group.objects.get(name=ROLE_FACULTY)
        self.faculty.groups.add(faculty_group)

        # Resource manager user
        self.manager = User.objects.create_user(username='manager1', email='m1@campus.edu', password='Pass123!')
        mgr_group = Group.objects.get(name=ROLE_RESOURCE_MANAGER)
        self.manager.groups.add(mgr_group)

        # Administrator user
        self.admin = User.objects.create_superuser(username='admin1', email='admin@campus.edu', password='Pass123!')

        # Sample resource & bookings
        self.resource = Resource.objects.create(
            name="Room 101",
            resource_type=ResourceType.CLASSROOM,
            location="Block A",
            capacity=30
        )
        now = timezone.now()
        self.booking_student = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            purpose="Study session",
            status=BookingStatus.PENDING
        )

    def test_dashboard_requires_login(self):
        """Unauthenticated user accessing dashboard must be redirected to login."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_role_identification(self):
        """Verify role strings returned by get_user_role helper."""
        self.assertEqual(get_user_role(self.admin), ROLE_ADMIN)
        self.assertEqual(get_user_role(self.manager), ROLE_RESOURCE_MANAGER)
        self.assertEqual(get_user_role(self.faculty), ROLE_FACULTY)
        self.assertEqual(get_user_role(self.student), ROLE_STUDENT)

    def test_object_level_booking_view_authorization(self):
        """User can view their own booking; another user cannot; admin/manager can."""
        # Student viewing own booking
        self.assertTrue(can_view_booking(self.student, self.booking_student))
        # Faculty viewing student's private booking is denied
        self.assertFalse(can_view_booking(self.faculty, self.booking_student))
        # Resource manager can view
        self.assertTrue(can_view_booking(self.manager, self.booking_student))
        # Administrator can view
        self.assertTrue(can_view_booking(self.admin, self.booking_student))

    def test_object_level_booking_cancel_authorization(self):
        """User can cancel own booking; another user cannot; admin can."""
        self.assertTrue(can_cancel_booking(self.student, self.booking_student))
        self.assertFalse(can_cancel_booking(self.faculty, self.booking_student))
        self.assertTrue(can_cancel_booking(self.admin, self.booking_student))

    def test_object_level_booking_manage_authorization(self):
        """Only admins and resource managers can approve/reject bookings."""
        self.assertFalse(can_manage_booking(self.student, self.booking_student))
        self.assertFalse(can_manage_booking(self.faculty, self.booking_student))
        self.assertTrue(can_manage_booking(self.manager, self.booking_student))
        self.assertTrue(can_manage_booking(self.admin, self.booking_student))

    def test_admin_required_decorator(self):
        """Test that @admin_or_staff_required blocks non-staff users with PermissionDenied."""
        @admin_or_staff_required
        def dummy_admin_view(request):
            return HttpResponse("Admin Access Granted")

        # Create mock request
        from django.test import RequestFactory
        factory = RequestFactory()
        req = factory.get('/admin-action/')

        # Student user is rejected
        req.user = self.student
        with self.assertRaises(PermissionDenied):
            dummy_admin_view(req)

        # Admin user is allowed
        req.user = self.admin
        res = dummy_admin_view(req)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content.decode(), "Admin Access Granted")
