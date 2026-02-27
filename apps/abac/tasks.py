"""Celery tasks for ABAC async processing."""

from celery import shared_task
from django.apps import apps


@shared_task(bind=True, name='abac.log_policy_evaluation')
def log_policy_evaluation(self, payload: dict) -> bool:
    """Persist ABAC evaluation logs asynchronously."""
    PolicyLog = apps.get_model('abac', 'PolicyLog')
    PolicyLog.objects.create(**payload)
    return True
