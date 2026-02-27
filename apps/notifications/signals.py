"""
Notification Signals
SECURITY FIX: Tenant-safe notifications
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.workflows.models import WorkflowInstance, WorkflowAction
from .services import NotificationService


@receiver(post_save, sender=WorkflowInstance)
def notify_approver_on_workflow(sender, instance, created, **kwargs):
    """
    Notify current approver when workflow progresses.

    🔒 SECURITY:
    - Enforce org isolation
    """
    if instance.status != 'in_progress':
        return

    if not instance.organization:
        return

    if not instance.current_approver:
        return

    NotificationService.notify(
        user=instance.current_approver.user,
        title=f"New Approval Required: {instance.workflow.name}",
        message=f"A new {instance.entity_type} request requires your approval.",
        notification_type='action_required',
        entity_type='workflow_instance',
        entity_id=instance.id,
        priority='high',
        organization_id=instance.organization_id
    )


@receiver(post_save, sender=WorkflowAction)
def notify_initiator_on_action(sender, instance, created, **kwargs):
    """
    Notify initiator on workflow action.

    🔒 SECURITY:
    - Explicit org context
    """
    if not created:
        return

    workflow = instance.workflow_instance
    if not workflow or not workflow.organization:
        return

    # Implement if initiator resolution exists
    # NotificationService.notify(
    #     user=workflow.initiator.user,
    #     ...
    #     organization_id=workflow.organization_id
    # )
