"""Payroll app permissions."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class PayrollTenantPermission(BasePermission):
    """Ensures request is scoped to an organization and objects match."""

    message = 'Organization context required for payroll operations.'

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
            if hasattr(obj, 'employee') and hasattr(obj.employee, 'organization_id'):
                obj_org = obj.employee.organization_id
        return obj_org is None or obj_org == organization.id


class CanManagePayroll(BasePermission):
    """HR admins and payroll managers can manage payroll runs."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return True
        return user.has_permission_for('payroll.manage')


class CanViewPayslip(BasePermission):
    """Employees can view own payslips; managers can view team payslips."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if user.has_permission_for('payroll.view_all'):
            return True
        employee = getattr(user, 'employee', None)
        if employee and hasattr(obj, 'employee_id') and obj.employee_id == employee.id:
            return True
        return False
