from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from datetime import timedelta, date

from resources.models import Resource, ResourceType, ResourceBlock
from campus_resolver.permissions import (
    ROLE_STUDENT, ROLE_RESOURCE_MANAGER, ensure_default_groups
)

User = get_user_model()


class ResourceModelTest(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(
            name="Computer Lab 101",
            resource_type=ResourceType.LAB,
            location="Building B, Floor 1",
            capacity=40,
            description="High-performance computing laboratory",
            is_active=True
        )

    def test_resource_creation(self):
        """Test Resource creation and __str__ representation."""
        self.assertEqual(self.resource.name, "Computer Lab 101")
        self.assertEqual(self.resource.resource_type, ResourceType.LAB)
        self.assertEqual(self.resource.capacity, 40)
        self.assertTrue(self.resource.is_active)
        self.assertIn("Computer Lab 101", str(self.resource))
        self.assertIn("Building B, Floor 1", str(self.resource))

    def test_resource_update(self):
        """Test updating resource attributes."""
        self.resource.capacity = 45
        self.resource.is_active = False
        self.resource.save()

        updated = Resource.objects.get(id=self.resource.id)
        self.assertEqual(updated.capacity, 45)
        self.assertFalse(updated.is_active)

    def test_resource_delete(self):
        """Test deleting a resource."""
        res_id = self.resource.id
        self.resource.delete()
        self.assertFalse(Resource.objects.filter(id=res_id).exists())

    def test_resource_block_clean_validation(self):
        """Test that ResourceBlock validates start_time < end_time."""
        now = timezone.now()
        invalid_block = ResourceBlock(
            resource=self.resource,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=1),
            reason="Repairs"
        )
        with self.assertRaises(ValidationError):
            invalid_block.clean()


class ResourceViewsTest(TestCase):
    def setUp(self):
        ensure_default_groups()
        self.client = Client()

        self.admin = User.objects.create_superuser(
            username='admin_res', email='admin_res@campus.edu', password='Password123!'
        )
        self.student = User.objects.create_user(
            username='student_res', email='student_res@campus.edu', password='Password123!'
        )
        student_group = Group.objects.get(name=ROLE_STUDENT)
        self.student.groups.add(student_group)

        self.lab1 = Resource.objects.create(
            name="Robotics Lab 101",
            resource_type=ResourceType.LAB,
            location="Engineering Wing A",
            capacity=30,
            is_active=True
        )
        self.hall1 = Resource.objects.create(
            name="Auditorium Central",
            resource_type=ResourceType.SEMINAR_HALL,
            location="Main Block",
            capacity=200,
            is_active=True
        )
        self.inactive_res = Resource.objects.create(
            name="Storage Hall (Closed)",
            resource_type=ResourceType.CLASSROOM,
            location="Old Annex",
            capacity=15,
            is_active=False
        )

    def test_resource_list_view(self):
        """Test resource listing returns 200 and shows active resources."""
        response = self.client.get(reverse('resources:resource_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Robotics Lab 101")
        self.assertContains(response, "Auditorium Central")
        # Inactive resource should NOT be shown to standard users
        self.assertNotContains(response, "Storage Hall (Closed)")

    def test_resource_search_filter(self):
        """Test search filter by query keyword."""
        response = self.client.get(reverse('resources:resource_list') + '?q=Robotics')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Robotics Lab 101")
        self.assertNotContains(response, "Auditorium Central")

    def test_resource_type_filter(self):
        """Test filtering by category."""
        response = self.client.get(reverse('resources:resource_list') + '?type=SEMINAR_HALL')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auditorium Central")
        self.assertNotContains(response, "Robotics Lab 101")

    def test_resource_capacity_filter(self):
        """Test filtering by min capacity."""
        response = self.client.get(reverse('resources:resource_list') + '?min_capacity=50')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auditorium Central")
        self.assertNotContains(response, "Robotics Lab 101")

    def test_resource_detail_view(self):
        """Test resource detail view renders correctly."""
        response = self.client.get(reverse('resources:resource_detail', kwargs={'pk': self.lab1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Robotics Lab 101")
        self.assertContains(response, "Engineering Wing A")
        self.assertContains(response, "30 persons/units")

    def test_resource_creation_by_admin(self):
        """Administrator can create a new resource."""
        self.client.login(username='admin_res', password='Password123!')
        response = self.client.post(reverse('resources:resource_create'), {
            'name': 'Physics Lab 305',
            'resource_type': ResourceType.LAB,
            'location': 'Science Wing',
            'capacity': 35,
            'description': 'Optics and lasers bench',
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Resource.objects.filter(name='Physics Lab 305').exists())

    def test_resource_creation_by_student_denied(self):
        """Standard student is denied from creating resources."""
        self.client.login(username='student_res', password='Password123!')
        response = self.client.post(reverse('resources:resource_create'), {
            'name': 'Hacker Lab',
            'resource_type': ResourceType.LAB,
            'location': 'Basement',
            'capacity': 10,
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Resource.objects.filter(name='Hacker Lab').exists())

    def test_resource_edit_by_admin(self):
        """Administrator can edit resource."""
        self.client.login(username='admin_res', password='Password123!')
        response = self.client.post(reverse('resources:resource_edit', kwargs={'pk': self.lab1.pk}), {
            'name': 'Robotics Lab 101 Renamed',
            'resource_type': ResourceType.LAB,
            'location': 'Engineering Wing A',
            'capacity': 50,
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.lab1.refresh_from_db()
        self.assertEqual(self.lab1.name, 'Robotics Lab 101 Renamed')
        self.assertEqual(self.lab1.capacity, 50)
