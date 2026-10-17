from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from resources.models import Resource, ResourceType, ResourceBlock


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
            end_time=now + timedelta(hours=1),  # end before start
            reason="Repairs"
        )
        with self.assertRaises(ValidationError):
            invalid_block.clean()
