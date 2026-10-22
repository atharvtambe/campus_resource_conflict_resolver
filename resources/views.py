from datetime import datetime, date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import Resource, ResourceType, ResourceBlock
from .forms import ResourceForm, ResourceBlockForm
from bookings.models import Booking, BookingStatus
from campus_resolver.permissions import (
    is_admin_or_staff, is_resource_manager, can_manage_resources, admin_or_staff_required, role_required, ROLE_RESOURCE_MANAGER
)


def resource_list(request):
    """
    Lists campus resources with full search, type filtering, location filtering,
    minimum capacity filtering, and pagination.
    """
    queryset = Resource.objects.all().order_by('name')

    # Non-staff/managers only see active resources by default unless specifically filtering
    can_manage = can_manage_resources(request.user)
    if not can_manage:
        queryset = queryset.filter(is_active=True)

    # Search query
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(location__icontains=q)
        )

    # Resource type filter
    resource_type = request.GET.get('type', '').strip()
    if resource_type:
        queryset = queryset.filter(resource_type=resource_type)

    # Location filter
    location_filter = request.GET.get('location', '').strip()
    if location_filter:
        queryset = queryset.filter(location__icontains=location_filter)

    # Minimum capacity filter
    min_capacity = request.GET.get('min_capacity', '').strip()
    if min_capacity.isdigit():
        queryset = queryset.filter(capacity__gte=int(min_capacity))

    # Active status filter (for staff/managers)
    status_filter = request.GET.get('status', '').strip()
    if can_manage and status_filter in ['active', 'inactive']:
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        else:
            queryset = queryset.filter(is_active=False)

    # Unique locations for filter dropdown
    distinct_locations = Resource.objects.values_list('location', flat=True).distinct()

    # Pagination: 6 items per page
    paginator = Paginator(queryset, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'resource_types': ResourceType.choices,
        'distinct_locations': distinct_locations,
        'search_q': q,
        'selected_type': resource_type,
        'selected_location': location_filter,
        'min_capacity': min_capacity,
        'selected_status': status_filter,
        'can_manage': can_manage,
        'total_count': queryset.count(),
    }
    return render(request, 'resources/resource_list.html', context)


def resource_detail(request, pk):
    """
    Shows detailed resource specifications, capacity, location, and date-specific availability schedule.
    """
    resource = get_object_or_404(Resource, pk=pk)
    can_manage = can_manage_resources(request.user)

    # Parse date query parameter (defaults to today)
    date_str = request.GET.get('date', '').strip()
    today = timezone.localdate()
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    # Start and end of the selected day in local time
    day_start = timezone.make_aware(datetime.combine(selected_date, datetime.min.time()))
    day_end = timezone.make_aware(datetime.combine(selected_date, datetime.max.time()))

    # Fetch confirmed or pending bookings overlapping with this date
    bookings_on_date = Booking.objects.filter(
        resource=resource,
        start_time__lt=day_end,
        end_time__gt=day_start,
        status__in=[BookingStatus.PENDING, BookingStatus.APPROVED]
    ).select_related('user').order_by('start_time')

    # Fetch maintenance blocks overlapping with this date
    blocks_on_date = ResourceBlock.objects.filter(
        resource=resource,
        start_time__lt=day_end,
        end_time__gt=day_start
    ).order_by('start_time')

    context = {
        'resource': resource,
        'can_manage': can_manage,
        'selected_date': selected_date,
        'today': today,
        'prev_date': selected_date - timedelta(days=1),
        'next_date': selected_date + timedelta(days=1),
        'bookings_on_date': bookings_on_date,
        'blocks_on_date': blocks_on_date,
    }
    return render(request, 'resources/resource_detail.html', context)


@login_required
def resource_create(request):
    """
    Allows authorized administrators and resource managers to add new resources.
    """
    if not can_manage_resources(request.user):
        messages.error(request, "Access Denied: Only administrators or resource managers can create resources.")
        return redirect('resources:resource_list')

    if request.method == 'POST':
        form = ResourceForm(request.POST)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f"Resource '{resource.name}' created successfully!")
            return redirect('resources:resource_detail', pk=resource.pk)
    else:
        form = ResourceForm()

    return render(request, 'resources/resource_form.html', {
        'form': form,
        'title': 'Add New Campus Resource',
        'is_edit': False,
    })


@login_required
def resource_edit(request, pk):
    """
    Allows authorized administrators and resource managers to update resource information.
    """
    if not can_manage_resources(request.user):
        messages.error(request, "Access Denied: Only administrators or resource managers can edit resources.")
        return redirect('resources:resource_list')

    resource = get_object_or_404(Resource, pk=pk)

    if request.method == 'POST':
        form = ResourceForm(request.POST, instance=resource)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f"Resource '{resource.name}' was successfully updated.")
            return redirect('resources:resource_detail', pk=resource.pk)
    else:
        form = ResourceForm(instance=resource)

    return render(request, 'resources/resource_form.html', {
        'form': form,
        'resource': resource,
        'title': f'Edit Resource: {resource.name}',
        'is_edit': True,
    })


@login_required
def resource_block_create(request, pk):
    """
    Allows adding scheduled maintenance time windows to a resource.
    """
    if not can_manage_resources(request.user):
        messages.error(request, "Access Denied: Only administrators or resource managers can block resources.")
        return redirect('resources:resource_detail', pk=pk)

    resource = get_object_or_404(Resource, pk=pk)

    if request.method == 'POST':
        form = ResourceBlockForm(request.POST)
        if form.is_valid():
            block = form.save(commit=False)
            block.resource = resource
            block.created_by = request.user
            block.save()
            messages.success(request, f"Maintenance block scheduled for {resource.name}.")
            return redirect('resources:resource_detail', pk=resource.pk)
    else:
        form = ResourceBlockForm()

    return render(request, 'resources/resource_block_form.html', {
        'form': form,
        'resource': resource,
    })
