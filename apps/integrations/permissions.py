"""Integrations app permissions."""
from rest_framework.permissions import BasePermission


class IntegrationsTenantPermission(BasePermission):
    """Organization-scoped access for integrations."""

    message = 'Organization context required.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, 'organization', None)
        )

    def has_object_permission(self, request, view, obj):
        organization = getattr(request, 'organization', None)
        if not organization:
            return False
        obj_org = getattr(obj, 'organization_id', None)
        return obj_org is None or obj_org == organization.id


class IsSuperuserOrOrgAdmin(BasePermission):
    """Only superusers and org admins can manage integrations."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or getattr(user, 'is_org_admin', False)
