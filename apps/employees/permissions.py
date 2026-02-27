"""Employee module permissions for tenant-safe HR workflows."""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class TenantOrganizationPermission(BasePermission):
    """Ensures the incoming request is scoped to a known organization and objects match it."""

    message = 'Organization context missing or mismatched.'

    def has_permission(self, request, view):
        organization = getattr(request, 'organization', None)
        return bool(request.user and request.user.is_authenticated and organization)

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False
        organization = getattr(request, 'organization', None)
        target_org_id = None
        if hasattr(obj, 'organization_id') and obj.organization_id:
            target_org_id = obj.organization_id
        elif hasattr(obj, 'employee') and getattr(obj.employee, 'organization_id', None):
            target_org_id = obj.employee.organization_id
        if target_org_id is None:
            return True
        return target_org_id == organization.id


class IsHRManagerOrSelf(BasePermission):
    """Allow HR managers full access, fallback to self-service for employee-owned records."""

    def has_permission(self, request, view):
        organization = getattr(request, 'organization', None)
        if not (request.user and request.user.is_authenticated and organization):
            return False
        if request.user.is_superuser or request.user.has_perm('employees.transitions'):
            return True
        employee = getattr(request.user, 'employee', None)
        if not employee or employee.organization_id != organization.id:
            return False
        # Allow self-service actions and safe reads for the employee's own record
        if view.action in SAFE_METHODS or view.action in ['create', 'my_resignation', 'list', 'withdraw']:
            return True
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.has_perm('employees.transitions'):
            return True
        employee = getattr(request.user, 'employee', None)
        if not employee:
            return False
        target_employee = getattr(obj, 'employee', None)
        return bool(target_employee and target_employee.id == employee.id)
