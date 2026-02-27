"""Enterprise workflow orchestration engine"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.employees.models import Employee
from apps.notifications.services import NotificationService
from apps.workflows.models import WorkflowAction, WorkflowDefinition, WorkflowInstance, WorkflowStep
from .approver_resolver import ApproverResolver
from .entity_resolver import EntityResolver, ResolvedEntity


@dataclass
class ActionPayload:
    action: str
    comments: str = ''
    forward_to: Optional[Employee] = None
    delegate_to: Optional[Employee] = None


class WorkflowEngine:
    """High-level workflow lifecycle manager."""

    @classmethod
    def start(cls, *, organization, entity_type: str, entity_id, initiator_user=None):
        if not organization:
            raise ValidationError({'organization': 'Organization context is required'})
        resolved = EntityResolver.resolve(
            organization_id=str(organization.id),
            entity_type=entity_type,
            entity_id=entity_id,
        )
        definition = cls._definition_for_type(organization, resolved.type_code)
        if not definition:
            raise ValidationError({'entity_type': f'No workflow defined for {entity_type}'})
        return cls._start_instance(definition, resolved, initiator_user)

    @classmethod
    def start_for_code(cls, *, entity, workflow_code: str, organization=None, initiator=None):
        organization = organization or getattr(entity, 'organization', None)
        if not organization:
            raise ValidationError({'organization': 'Workflow start requires organization'})
        definition = WorkflowDefinition.objects.filter(
            organization=organization,
            code=workflow_code,
            is_active=True,
        ).first()
        if not definition:
            raise ValidationError({'workflow_code': f'Workflow {workflow_code} not found'})
        resolved = ResolvedEntity(type_code=entity._meta.model_name, instance=entity)
        return cls._start_instance(definition, resolved, getattr(initiator, 'user', initiator))

    @classmethod
    def take_action(cls, instance: WorkflowInstance, *, actor: Employee, payload: ActionPayload):
        if instance.status != 'in_progress':
            raise ValidationError({'status': 'Workflow is no longer active'})
        if not actor or actor.organization_id != instance.organization_id:
            raise ValidationError({'actor': 'Actor must belong to the same organization'})
        if payload.action not in {'approve', 'reject', 'forward', 'delegate'}:
            raise ValidationError({'action': 'Unsupported action'})
        if instance.current_approver and instance.current_approver != actor and payload.action in {'approve', 'reject'}:
            raise ValidationError({'actor': 'Only the assigned approver can perform this action'})

        if payload.action == 'forward':
            cls._forward(instance, actor, payload)
            return instance
        if payload.action == 'delegate':
            cls._delegate(instance, actor, payload)
            return instance
        if payload.action == 'approve':
            cls._approve(instance, actor, payload.comments)
            return instance
        if payload.action == 'reject':
            if not payload.comments:
                raise ValidationError({'comments': 'Comments required when rejecting'})
            cls._reject(instance, actor, payload.comments)
            return instance
        return instance

    @classmethod
    def escalate(cls, instance: WorkflowInstance, *, actor: Optional[Employee], reason: str, target: Optional[Employee] = None):
        if instance.status != 'in_progress':
            raise ValidationError({'status': 'Only in-progress workflows can be escalated'})
        if actor and actor.organization_id != instance.organization_id:
            raise ValidationError({'actor': 'Actor must belong to the same organization'})
        target_employee = target or cls._escalation_target(instance)
        if not target_employee:
            raise ValidationError({'escalate_to': 'Unable to determine escalation target'})

        cls._log_action(instance, actor=actor, action='escalated', comments=reason)
        instance.status = 'escalated'
        instance.current_approver = target_employee
        instance.save(update_fields=['status', 'current_approver', 'updated_at'])
        cls._notify(instance, event='workflow.escalated', employees=[target_employee], context={'reason': reason})
        return instance

    @classmethod
    def handle_sla_breach(cls, instance: WorkflowInstance):
        workflow = instance.workflow
        if not workflow:
            return instance
        if workflow.auto_approve_on_sla:
            cls._auto_complete(instance)
        else:
            cls.escalate(instance, actor=None, reason='SLA breach')
        return instance

    # ------------------------------------------------------------------ internals
    @classmethod
    @transaction.atomic
    def _start_instance(cls, definition: WorkflowDefinition, resolved: ResolvedEntity, initiator_user):
        first_step = definition.workflow_steps.filter(is_active=True).order_by('order').first()
        instance = WorkflowInstance.objects.create(
            workflow=definition,
            entity_type=resolved.type_code,
            entity_id=resolved.instance.id,
            current_step=first_step.order if first_step else 0,
            status='in_progress',
            organization=definition.organization,
            created_by=initiator_user,
        )
        initiator_employee = cls._employee_from_user(initiator_user)
        cls._log_action(instance, actor=initiator_employee, action='started', comments='Workflow initiated')

        if not first_step:
            cls._complete(instance, resolved, approved=True, actor=initiator_employee, auto=True)
            return instance

        approver = ApproverResolver.resolve(
            step=first_step,
            entity=resolved.instance,
            initiator=initiator_employee,
            organization_id=definition.organization_id,
        )
        if approver is None:
            cls._complete(instance, resolved, approved=True, actor=initiator_employee, auto=True)
            return instance

        instance.current_approver = approver
        instance.save(update_fields=['current_approver'])
        cls._notify(instance, event='workflow.started', employees=[approver, initiator_employee], context={'step': first_step.name})
        return instance

    @classmethod
    def _approve(cls, instance: WorkflowInstance, actor: Employee, comments: str):
        resolved = cls._resolve_entity(instance)
        cls._log_action(instance, actor=actor, action='approved', comments=comments)
        next_step = cls._next_step(instance)
        if not next_step:
            cls._complete(instance, resolved, approved=True, actor=actor)
            return
        next_approver = ApproverResolver.resolve(
            step=next_step,
            entity=resolved.instance,
            initiator=cls._employee_from_user(instance.created_by),
            organization_id=instance.organization_id,
        )
        if not next_approver:
            cls._complete(instance, resolved, approved=True, actor=actor)
            return
        instance.current_step = next_step.order
        instance.current_approver = next_approver
        instance.status = 'in_progress'
        instance.save(update_fields=['current_step', 'current_approver', 'status'])
        cls._notify(instance, event='workflow.step_assigned', employees=[next_approver], context={'step': next_step.name})

    @classmethod
    def _reject(cls, instance: WorkflowInstance, actor: Employee, comments: str):
        resolved = cls._resolve_entity(instance)
        cls._log_action(instance, actor=actor, action='rejected', comments=comments)
        instance.status = 'rejected'
        instance.current_approver = None
        instance.completed_at = timezone.now()
        instance.save(update_fields=['status', 'current_approver', 'completed_at'])
        EntityResolver.update_entity_status(resolved.instance, status='rejected')
        cls._notify(instance, event='workflow.rejected', employees=cls._stakeholders(resolved, actor), context={'comments': comments})

    @classmethod
    def _forward(cls, instance: WorkflowInstance, actor: Employee, payload: ActionPayload):
        if not payload.forward_to:
            raise ValidationError({'forward_to': 'Forward action requires target employee'})
        cls._log_action(instance, actor=actor, action='forwarded', comments=payload.comments or 'Forwarded approval')
        instance.current_approver = payload.forward_to
        instance.save(update_fields=['current_approver'])
        cls._notify(instance, event='workflow.step_assigned', employees=[payload.forward_to], context={'forwarded_by': actor.full_name})

    @classmethod
    def _delegate(cls, instance: WorkflowInstance, actor: Employee, payload: ActionPayload):
        if not payload.delegate_to:
            raise ValidationError({'delegate_to': 'Delegate action requires target employee'})
        cls._log_action(instance, actor=actor, action='delegated', comments=payload.comments or 'Delegated approval')
        instance.current_approver = payload.delegate_to
        instance.save(update_fields=['current_approver'])
        cls._notify(instance, event='workflow.step_assigned', employees=[payload.delegate_to], context={'delegated_by': actor.full_name})

    @classmethod
    def _complete(cls, instance: WorkflowInstance, resolved: ResolvedEntity, *, approved: bool, actor: Optional[Employee], auto: bool = False):
        instance.status = 'approved' if approved else 'rejected'
        instance.current_approver = None
        instance.completed_at = timezone.now()
        instance.save(update_fields=['status', 'current_approver', 'completed_at'])
        EntityResolver.update_entity_status(resolved.instance, status=instance.status)
        action = 'auto_approved' if auto and approved else ('auto_rejected' if auto else ('approved' if approved else 'rejected'))
        cls._log_action(instance, actor=actor, action=action, comments='Auto completion' if auto else 'Workflow completed')
        event = 'workflow.completed' if approved else 'workflow.rejected'
        cls._notify(instance, event=event, employees=cls._stakeholders(resolved, actor))

    @classmethod
    def _auto_complete(cls, instance: WorkflowInstance):
        resolved = cls._resolve_entity(instance)
        cls._complete(instance, resolved, approved=True, actor=None, auto=True)

    @staticmethod
    def _definition_for_type(organization, entity_type):
        return WorkflowDefinition.objects.filter(
            organization=organization,
            entity_type=entity_type,
            is_active=True,
        ).first()

    @staticmethod
    def _next_step(instance: WorkflowInstance) -> Optional[WorkflowStep]:
        if not instance.workflow:
            return None
        return instance.workflow.workflow_steps.filter(order__gt=instance.current_step, is_active=True).order_by('order').first()

    @staticmethod
    def _employee_from_user(user):
        if not user:
            return None
        return getattr(user, 'employee', None)

    @classmethod
    def _resolve_entity(cls, instance: WorkflowInstance) -> ResolvedEntity:
        if not instance.organization_id:
            raise ValidationError({'organization': 'Workflow instance missing organization context'})
        return EntityResolver.resolve(
            organization_id=str(instance.organization_id),
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
        )

    @staticmethod
    def _stakeholders(resolved: ResolvedEntity, actor: Optional[Employee]):
        primary = EntityResolver.primary_employee(resolved.instance)
        recipients = set()
        if primary:
            recipients.add(primary)
        if actor:
            recipients.add(actor)
        return [emp for emp in recipients if emp]

    @staticmethod
    def _log_action(instance, *, actor, action: str, comments: str):
        WorkflowAction.objects.create(
            instance=instance,
            step=instance.current_step,
            actor=actor,
            action=action,
            comments=comments or '',
            organization=instance.organization,
        )

    @classmethod
    def _notify(cls, instance: WorkflowInstance, *, event: str, employees: Iterable[Optional[Employee]], context: Optional[dict] = None):
        context = context or {}
        for employee in filter(None, employees):
            NotificationService.notify(
                organization_id=str(instance.organization_id),
                employee=employee,
                subject=f"Workflow update: {instance.workflow.name if instance.workflow else instance.id}",
                body=f"Event: {event}\nStatus: {instance.status}",
                entity_type='workflow_instance',
                entity_id=instance.id,
                metadata={'event': event, **context},
            )

    @classmethod
    def _escalation_target(cls, instance: WorkflowInstance) -> Optional[Employee]:
        if not instance.workflow:
            return None
        current_step = instance.workflow.workflow_steps.filter(order=instance.current_step).first()
        if current_step and current_step.escalate_to:
            resolved = cls._resolve_entity(instance)
            return ApproverResolver.resolve(
                step=current_step.escalate_to,
                entity=resolved.instance,
                initiator=cls._employee_from_user(instance.created_by),
                organization_id=instance.organization_id,
            )
        if instance.current_approver and instance.current_approver.reporting_manager:
            return instance.current_approver.reporting_manager
        return None
