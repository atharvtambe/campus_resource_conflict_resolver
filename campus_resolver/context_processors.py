from .permissions import get_user_role, is_admin_or_staff, is_resource_manager


def auth_role_context(request):
    """
    Context processor adding user role information to all templates.
    """
    if request.user.is_authenticated:
        role = get_user_role(request.user)
        return {
            'user_role': role,
            'is_admin_or_staff': is_admin_or_staff(request.user),
            'is_resource_manager': is_resource_manager(request.user),
        }
    return {
        'user_role': 'Anonymous',
        'is_admin_or_staff': False,
        'is_resource_manager': False,
    }
