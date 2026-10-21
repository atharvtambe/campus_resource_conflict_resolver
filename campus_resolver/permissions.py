"""
Permissions, Roles, and Access Control for Campus Resource Conflict Resolver.
Supports Django Groups (Student, Faculty, Resource Manager) and staff/superuser permissions.
"""

from functools import wraps
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages

# Role definitions
ROLE_STUDENT = 'Student'
ROLE_FACULTY = 'Faculty'
ROLE_RESOURCE_MANAGER = 'Resource Manager'
ROLE_ADMIN = 'Administrator'

DEFAULT_ROLES = [ROLE_STUDENT, ROLE_FACULTY, ROLE_RESOURCE_MANAGER]


def ensure_default_groups():
    """
    Ensures that default role groups exist in the database.
    """
    for role_name in DEFAULT_ROLES:
        Group.objects.get_or_create(name=role_name)


def is_admin_or_staff(user):
    """Checks if the user has administrative privileges."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def is_resource_manager(user):
    """Checks if user is in Resource Manager group or is an administrator."""
    if not user.is_authenticated:
        return False
    return is_admin_or_staff(user) or user.groups.filter(name=ROLE_RESOURCE_MANAGER).exists()


def is_faculty(user):
    """Checks if user belongs to Faculty group."""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=ROLE_FACULTY).exists()


def is_student(user):
    """Checks if user belongs to Student group."""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=ROLE_STUDENT).exists()


def get_user_role(user):
    """
    Returns a human-readable role string for the user for UI display and role checks.
    """
    if not user or not user.is_authenticated:
        return 'Anonymous'
    if user.is_superuser or user.is_staff:
        return ROLE_ADMIN
    if user.groups.filter(name=ROLE_RESOURCE_MANAGER).exists():
        return ROLE_RESOURCE_MANAGER
    if user.groups.filter(name=ROLE_FACULTY).exists():
        return ROLE_FACULTY
    if user.groups.filter(name=ROLE_STUDENT).exists():
        return ROLE_STUDENT
    return 'User'


# Decorators
def admin_or_staff_required(view_func):
    """
    Decorator to restrict view access strictly to administrators or staff members.
    Raises PermissionDenied (403) for non-admin authenticated users.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to access this page.")
            return redirect('login')
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("You do not have administrative privileges to perform this action.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def role_required(*allowed_roles):
    """
    Decorator that verifies if the user belongs to at least one of the specified roles,
    or has administrator / staff access.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access this page.")
                return redirect('login')
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            user_groups = request.user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in allowed_roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("You do not have the required role permissions to view this page.")
        return _wrapped_view
    return decorator


# Object-level authorization checks
def can_view_booking(user, booking):
    """A user can view their own booking or any booking if they are admin/manager."""
    if not user.is_authenticated:
        return False
    return booking.user_id == user.id or is_resource_manager(user)


def can_cancel_booking(user, booking):
    """A user can cancel their own pending/approved booking or admin can cancel."""
    if not user.is_authenticated:
        return False
    return booking.user_id == user.id or is_admin_or_staff(user)


def can_manage_booking(user, booking=None):
    """Admins and Resource Managers can approve/reject bookings."""
    if not user.is_authenticated:
        return False
    return is_resource_manager(user)


def can_manage_resources(user):
    """Admins and Resource Managers can create, update, or deactivate resources."""
    if not user.is_authenticated:
        return False
    return is_resource_manager(user)
