"""
Workflow Signals - Integration with other modules
SECURITY FIX: Explicit tenant propagation
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.leave.models import LeaveRequest
from .services import WorkflowEngine


@receiver(post_save, sender=LeaveRequest)
def trigger_leave_workflow(sender, instance, created, **kwargs):
    """
    Automatically start a workflow instance when a new leave request is created.

    🔒 SECURITY:
    - Explicitly pass organization
    - Never rely on thread-local org context
    """
    if not created:
        return

    organization = instance.branch.organization if instance.branch else None
    if not organization:
        return  # Hard stop if org missing

    WorkflowEngine.start_for_code(
        entity=instance,
        workflow_code='LEAVE_REQUEST',
        initiator=instance.employee,
        organization=organization
    )
