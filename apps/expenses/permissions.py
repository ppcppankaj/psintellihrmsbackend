"""Expenses app permissions."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class ExpensesTenantPermission(BasePermission):
    """Organization-scoped access for expenses."""

    message = 'Organization context required for expense operations.'

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
        if obj_org is None and hasattr(obj, 'employee'):
            obj_org = getattr(obj.employee, 'organization_id', None)
        return obj_org is None or obj_org == organization.id


class CanManageExpenses(BasePermission):
    """Finance / HR can manage all expenses; employees manage their own."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return True  # all employees can submit

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if user.has_permission_for('expenses.manage'):
            return True
        employee = getattr(user, 'employee', None)
        if employee and hasattr(obj, 'employee_id') and obj.employee_id == employee.id:
            return True
        return request.method in SAFE_METHODS
