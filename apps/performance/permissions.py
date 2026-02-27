"""Performance app permissions."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class PerformanceTenantPermission(BasePermission):
    """Organization-scoped access for performance management."""

    message = 'Organization context required for performance operations.'

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


class CanManagePerformance(BasePermission):
    """HR admins can manage performance; employees can view own."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return True
        return user.has_permission_for('performance.manage')

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.has_permission_for('performance.view_all'):
            return True
        employee = getattr(user, 'employee', None)
        if employee and hasattr(obj, 'employee_id') and obj.employee_id == employee.id:
            return True
        return False
