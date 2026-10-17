from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class BookingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Booking(models.Model):
    """
    Represents a reservation request for a campus resource and its approval status.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    start_time = models.DateTimeField(help_text="Booking start time (inclusive)")
    end_time = models.DateTimeField(help_text="Booking end time (exclusive)")
    purpose = models.TextField(help_text="Purpose or justification of the reservation")
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['resource', 'start_time', 'end_time'], name='idx_bk_res_time'),
            models.Index(fields=['status'], name='idx_bk_status'),
            models.Index(fields=['user', 'created_at'], name='idx_bk_user_created'),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': "Booking start time must be strictly before end time."})

        if hasattr(self, 'resource') and self.resource:
            if not self.resource.is_active:
                raise ValidationError({'resource': "This resource is currently inactive and cannot be booked."})

    def __str__(self):
        return f"Booking #{self.id or 'New'} - {self.resource.name} by {self.user.username} ({self.status})"


class BookingHistory(models.Model):
    """
    Records status changes, cancellations, and approvals with audit trail.
    """
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking_status_changes'
    )
    old_status = models.CharField(max_length=20, choices=BookingStatus.choices, blank=True, default='')
    new_status = models.CharField(max_length=20, choices=BookingStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['booking', 'changed_at'], name='idx_bkhist_booking_time'),
            models.Index(fields=['new_status'], name='idx_bkhist_new_status'),
        ]

    def __str__(self):
        return f"History #{self.id} for Booking #{self.booking_id}: {self.old_status} -> {self.new_status}"
