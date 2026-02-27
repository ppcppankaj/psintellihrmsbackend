"""Celery task to deliver notifications"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.core.celery_tasks import TenantAwareTask
from apps.notifications.models import Notification
from apps.notifications.services.notification_service import NotificationService


@shared_task(bind=True, name='notifications.send_notification')
def send_notification_task(self, organization_id: str, notification_id: str):
    organization = TenantAwareTask.get_organization(organization_id)
    if not organization:
        return

    notification = (
        Notification.objects.select_related('recipient__user')
        .filter(id=notification_id, organization=organization)
        .first()
    )
    if not notification:
        return

    if notification.scheduled_for and notification.scheduled_for > timezone.now():
        # Reschedule if triggered prematurely.
        send_notification_task.apply_async(
            kwargs={'organization_id': organization_id, 'notification_id': notification_id},
            eta=notification.scheduled_for,
        )
        return

    NotificationService.dispatch_immediately(notification)
