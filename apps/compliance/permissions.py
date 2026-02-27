"""Compliance app permissions."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class ComplianceTenantPermission(BasePermission):
    """Organization-scoped access for compliance."""

    message = 'Organization context required for compliance operations.'

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


class CanManageCompliance(BasePermission):
    """Only admins and compliance officers can manage compliance records."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return user.has_permission_for('compliance.view')
        return user.has_permission_for('compliance.manage')
