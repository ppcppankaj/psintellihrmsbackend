"""
Billing permissions
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class BillingTenantPermission(BasePermission):
    """Ensures request is scoped to an organization."""
    message = 'Organization context required for billing operations.'

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
        if obj_org is None:
            return True
        return obj_org == organization.id


class IsSuperUserOnly(BasePermission):
    """Full CRUD restricted to superusers."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class IsSuperUserOrReadOnly(BasePermission):
    """Read access for any authenticated user; writes restricted to superusers."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_superuser


class IsOrgAdminOrReadOnly(BasePermission):
    """Read for authenticated; writes for org admin or superuser."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_superuser:
            return True
        return bool(getattr(request.user, 'is_org_admin', False))


class IsOrgAdmin(BasePermission):
    """Only org admins or superusers."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return bool(getattr(request.user, 'is_org_admin', False))
