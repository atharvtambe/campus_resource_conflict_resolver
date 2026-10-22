from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from resources.models import Resource
from .models import Booking, BookingStatus
from .services import has_booking_conflict, get_conflicting_bookings, get_conflicting_maintenance_blocks


class BookingForm(forms.ModelForm):
    """
    Booking creation form with half-open interval conflict validation and active resource filtering.
    """
    resource = forms.ModelChoiceField(
        queryset=Resource.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="-- Select an available campus resource --"
    )
    start_time = forms.DateTimeField(
        label="Start Time",
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        help_text="Beginning of reservation (inclusive)"
    )
    end_time = forms.DateTimeField(
        label="End Time",
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        help_text="End of reservation (exclusive)"
    )
    purpose = forms.CharField(
        label="Purpose / Event Details",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'State the objective, academic course, student club, or estimated attendees...'
        }),
        help_text="Describe why this resource is needed for review."
    )

    class Meta:
        model = Booking
        fields = ['resource', 'start_time', 'end_time', 'purpose']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Refresh active resources queryset
        self.fields['resource'].queryset = Resource.objects.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        resource = cleaned_data.get('resource')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if not resource or not start_time or not end_time:
            return cleaned_data

        # 1. Resource active validation
        if not resource.is_active:
            self.add_error('resource', f"Resource '{resource.name}' is currently inactive and cannot be booked.")

        # 2. Start time must be before End time
        if start_time >= end_time:
            self.add_error('end_time', "Booking start time must be strictly earlier than end time.")
            return cleaned_data

        # 3. Minimum duration validation (e.g. at least 15 minutes)
        if (end_time - start_time) < timedelta(minutes=15):
            self.add_error('end_time', "Booking duration must be at least 15 minutes.")

        # 4. Conflict detection using half-open intervals
        exclude_id = self.instance.id if self.instance and self.instance.id else None
        if has_booking_conflict(resource, start_time, end_time, exclude_booking_id=exclude_id):
            conflicts = get_conflicting_bookings(resource, start_time, end_time, exclude_booking_id=exclude_id)
            blocks = get_conflicting_maintenance_blocks(resource, start_time, end_time)

            conflict_details = []
            for c in conflicts[:3]:
                conflict_details.append(
                    f"Booking #{c.id} ({c.start_time.strftime('%H:%M')} - {c.end_time.strftime('%H:%M')})"
                )
            for b in blocks[:2]:
                conflict_details.append(
                    f"Maintenance ({b.start_time.strftime('%H:%M')} - {b.end_time.strftime('%H:%M')}: {b.reason})"
                )

            detail_str = f" Conflicting intervals: {', '.join(conflict_details)}." if conflict_details else ""
            raise ValidationError(
                f"Schedule Conflict: Resource '{resource.name}' is already reserved or blocked during this time interval.{detail_str} Please select an alternative slot."
            )

        return cleaned_data
