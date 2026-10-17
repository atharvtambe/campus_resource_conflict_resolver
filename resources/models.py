from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class ResourceType(models.TextChoices):
    LAB = 'LAB', 'Laboratory'
    CLASSROOM = 'CLASSROOM', 'Classroom'
    SEMINAR_HALL = 'SEMINAR_HALL', 'Seminar Hall'
    PROJECTOR = 'PROJECTOR', 'Projector'
    EQUIPMENT = 'EQUIPMENT', 'Equipment'
    OTHER = 'OTHER', 'Other'


class Resource(models.Model):
    """
    Represents a campus resource such as a room, lab, seminar hall, or equipment.
    """
    name = models.CharField(max_length=150, help_text="Resource name (e.g. Lab 301, Auditorium A)")
    resource_type = models.CharField(
        max_length=50,
        choices=ResourceType.choices,
        default=ResourceType.CLASSROOM,
        help_text="Category of the resource"
    )
    location = models.CharField(max_length=200, help_text="Building, floor, or room details")
    capacity = models.PositiveIntegerField(
        default=1,
        help_text="Maximum capacity (for rooms/labs) or quantity (for equipment)"
    )
    description = models.TextField(blank=True, default='', help_text="Resource description and available equipment")
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this resource is currently available for bookings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['resource_type'], name='idx_resource_type'),
            models.Index(fields=['is_active'], name='idx_resource_active'),
            models.Index(fields=['location'], name='idx_resource_location'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_resource_type_display()}) - {self.location}"


class ResourceBlock(models.Model):
    """
    Represents maintenance periods or blocked time windows when a resource is unavailable.
    """
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='maintenance_blocks'
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    reason = models.CharField(max_length=255, default='Scheduled Maintenance')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_blocks'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['resource', 'start_time', 'end_time'], name='idx_resblock_time'),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({'end_time': "End time must be strictly after start time."})

    def __str__(self):
        return f"Block on {self.resource.name} ({self.start_time:%Y-%m-%d %H:%M} to {self.end_time:%H:%M})"
