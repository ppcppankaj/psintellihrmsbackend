"""Assets app permissions."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class AssetsTenantPermission(BasePermission):
    """Organization-scoped access for assets."""

    message = 'Organization context required for asset operations.'

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


class CanManageAssets(BasePermission):
    """Admins can CRUD assets; employees can only view and create requests."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return True
        return user.has_permission_for('assets.manage')


class CanRequestAsset(BasePermission):
    """All authenticated employees can request assets."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        employee = getattr(user, 'employee', None)
        if employee and hasattr(obj, 'employee_id') and obj.employee_id == employee.id:
            return True
        return user.has_permission_for('assets.manage')
