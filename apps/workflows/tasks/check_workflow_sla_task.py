"""Celery task to enforce workflow SLAs"""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.workflows.models import WorkflowInstance
from apps.workflows.services import WorkflowEngine


@shared_task(bind=True, name='workflows.check_sla')
def check_workflow_sla_task(self):
    """Scan active workflow instances and escalate or auto-complete on SLA breach."""
    now = timezone.now()
    queryset = WorkflowInstance.objects.select_related('workflow').filter(status='in_progress')
    breached = []
    for instance in queryset:
        workflow = instance.workflow
        if not workflow or not workflow.sla_hours:
            continue
        deadline = instance.started_at + timedelta(hours=workflow.sla_hours)
        if deadline <= now:
            breached.append(instance)
    for instance in breached:
        WorkflowEngine.handle_sla_breach(instance)
    return {'checked': queryset.count(), 'breached': len(breached)}
