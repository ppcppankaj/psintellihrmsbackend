"""Entity resolution for workflow orchestration"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Model


ENTITY_MODEL_MAP: Dict[str, Tuple[str, str]] = {
    'leave_request': ('leave', 'LeaveRequest'),
    'payroll_run': ('payroll', 'PayrollRun'),
    'employee_transfer': ('employees', 'EmployeeTransfer'),
    'employee_promotion': ('employees', 'EmployeePromotion'),
    'employee_loan': ('payroll', 'EmployeeLoan'),
    'loan': ('payroll', 'EmployeeLoan'),
    'reimbursement': ('payroll', 'ReimbursementClaim'),
    'expense_claim': ('expenses', 'ExpenseClaim'),
    'expense': ('expenses', 'ExpenseClaim'),
    'resignation_request': ('employees', 'ResignationRequest'),
    'meeting': ('chat', 'MeetingSchedule'),
    'fnf': ('payroll', 'FullFinalSettlement'),
    'full_final_settlement': ('payroll', 'FullFinalSettlement'),
    'ai_decision': ('ai_services', 'AIPrediction'),
}

ENTITY_TYPE_CHOICES = tuple((key, key.replace('_', ' ').title()) for key in ENTITY_MODEL_MAP.keys())


def _normalize(entity_type: str) -> str:
    token = (entity_type or '').strip()
    if not token:
        raise ValidationError({'entity_type': 'Entity type is required'})
    buffer = []
    for char in token:
        if char.isupper():
            buffer.append('_')
            buffer.append(char.lower())
        elif char in {'-', ' '}:
            buffer.append('_')
        else:
            buffer.append(char.lower())
    normalized = ''.join(buffer).strip('_')
    return normalized


@dataclass
class ResolvedEntity:
    type_code: str
    instance: Model

    @property
    def organization_id(self):
        return getattr(self.instance, 'organization_id', None)

    @property
    def employee(self):
        return getattr(self.instance, 'employee', None)


class EntityResolver:
    """Resolve workflow entities across modules with tenant safety."""

    @classmethod
    def resolve(cls, *, organization_id: str, entity_type: str, entity_id) -> ResolvedEntity:
        normalized = _normalize(entity_type)
        model_path = ENTITY_MODEL_MAP.get(normalized)
        if not model_path:
            raise ValidationError({'entity_type': f'Unsupported entity type: {entity_type}'})
        ModelClass = apps.get_model(model_path[0], model_path[1])
        queryset = ModelClass.objects.filter(id=entity_id)
        if hasattr(ModelClass, 'organization_id'):
            queryset = queryset.filter(organization_id=organization_id)
        entity = queryset.first()
        if not entity:
            raise ValidationError({'entity_id': 'Entity not found for organization'})
        return ResolvedEntity(type_code=normalized, instance=entity)

    @staticmethod
    def update_entity_status(entity: Model, *, status: str) -> None:
        if hasattr(entity, 'status'):
            setattr(entity, 'status', status)
            entity.save(update_fields=['status'])

    @staticmethod
    def primary_employee(entity: Model):
        if hasattr(entity, 'employee'):
            return entity.employee
        if hasattr(entity, 'initiator'):
            return getattr(entity, 'initiator', None)
        if hasattr(entity, 'requester'):
            return getattr(entity, 'requester', None)
        return None

    @classmethod
    def supported_types(cls):
        return tuple(ENTITY_MODEL_MAP.keys())
