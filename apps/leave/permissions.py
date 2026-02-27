"""Leave module specific permissions."""

from rest_framework.permissions import BasePermission


class LeaveTenantPermission(BasePermission):
    """Ensures requests operate within the active organization context."""

    message = 'Tenant context missing or object outside organization scope.'

    def has_permission(self, request, view):
        organization = getattr(request, 'organization', None)
        return organization is not None

    def has_object_permission(self, request, view, obj):
        organization = getattr(request, 'organization', None)
        if organization is None:
            return False
        obj_org = getattr(obj, 'organization_id', None)
        return obj_org in (None, organization.id)
