"""Attendance-specific permission classes."""

from rest_framework.permissions import BasePermission


class AttendanceTenantPermission(BasePermission):
    """Ensures every request/object is scoped to the active tenant."""

    message = 'Attendance resources must be accessed through an active organization context.'

    def has_permission(self, request, view):
        return bool(getattr(request, 'organization', None))

    def has_object_permission(self, request, view, obj):
        organization = getattr(request, 'organization', None)
        if not organization:
            return False
        obj_org_id = self._resolve_org_id(obj)
        return obj_org_id in (None, organization.id)

    @staticmethod
    def _resolve_org_id(obj):
        if obj is None:
            return None
        if hasattr(obj, 'organization_id'):
            return obj.organization_id
        organization = getattr(obj, 'organization', None)
        return getattr(organization, 'id', None)
