"""Approver resolution logic for workflow steps"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from django.core.exceptions import ValidationError

from apps.employees.models import Employee

if TYPE_CHECKING:  # pragma: no cover
    from apps.workflows.models import WorkflowStep


class ApproverResolver:
    """Determine the employee responsible for a workflow step."""

    @classmethod
    def resolve(
        cls,
        *,
        step: 'WorkflowStep',
        entity=None,
        initiator=None,
        organization_id=None,
    ) -> Optional[Employee]:
        handler = {
            'reporting_manager': cls._reporting_manager,
            'hr_manager': cls._hr_manager,
            'department_head': cls._department_head,
            'role': cls._role_based,
            'user': cls._specific_user,
        }.get(step.approver_type)
        if not handler:
            raise ValidationError({'approver_type': f'Unsupported approver type: {step.approver_type}'})
        employee = handler(step=step, entity=entity, initiator=initiator, organization_id=organization_id)
        if employee and organization_id and str(employee.organization_id) != str(organization_id):
            raise ValidationError({'approver_user': 'Approver must belong to the same organization'})
        return employee

    @staticmethod
    def _reporting_manager(step, entity, **_):
        employee = getattr(entity, 'employee', None)
        if employee and employee.reporting_manager:
            return employee.reporting_manager
        return None

    @staticmethod
    def _hr_manager(step, entity, **_):
        employee = getattr(entity, 'employee', None)
        if employee and employee.hr_manager:
            return employee.hr_manager
        return None

    @staticmethod
    def _department_head(step, entity, **_):
        employee = getattr(entity, 'employee', None)
        department = getattr(employee, 'department', None) if employee else None
        if department and department.head:
            return department.head
        return None

    @staticmethod
    def _role_based(step, entity, organization_id=None, **_):
        if not step.approver_role:
            raise ValidationError({'approver_role': 'Role approver requires approver_role'})
        queryset = Employee.objects.filter(
            user__user_roles__role=step.approver_role,
            user__user_roles__is_active=True,
            is_active=True,
        )
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        employee = getattr(entity, 'employee', None)
        if employee and employee.department_id:
            queryset = queryset.filter(department_id=employee.department_id)
        return queryset.order_by('employee_id').first()

    @staticmethod
    def _specific_user(step, **_):
        return step.approver_user
