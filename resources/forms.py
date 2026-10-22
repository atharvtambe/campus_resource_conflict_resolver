from django import forms
from django.core.exceptions import ValidationError
from .models import Resource, ResourceBlock


class ResourceForm(forms.ModelForm):
    """
    Form for authorized administrators/managers to create and update campus resources.
    """
    class Meta:
        model = Resource
        fields = ['name', 'resource_type', 'location', 'capacity', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Physics Lab 301, Auditorium'}),
            'resource_type': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Science Block, 3rd Floor'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe available facilities, equipment, or policies'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_capacity(self):
        capacity = self.cleaned_data.get('capacity')
        if capacity is not None and capacity < 1:
            raise ValidationError("Capacity must be at least 1.")
        return capacity


class ResourceBlockForm(forms.ModelForm):
    """
    Form to schedule maintenance windows and block times on a resource.
    """
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
    )
    end_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
    )

    class Meta:
        model = ResourceBlock
        fields = ['start_time', 'end_time', 'reason']
        widgets = {
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Annual HVAC maintenance, Hardware upgrades'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')
        if start and end and start >= end:
            self.add_error('end_time', "Maintenance end time must be after start time.")
        return cleaned_data
