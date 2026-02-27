"""Celery tasks for individual billing email notifications."""
import logging

from celery import shared_task

from apps.billing.models import OrganizationSubscription

logger = logging.getLogger(__name__)


def _load_subscription(subscription_id):
    return (
        OrganizationSubscription.objects.select_related('organization', 'plan')
        .filter(id=subscription_id)
        .first()
    )


def _send_event_email(subscription_id, event_key):
    from apps.billing.services import RenewalEmailService

    subscription = _load_subscription(subscription_id)
    if not subscription:
        logger.warning('Subscription %s not found for %s email', subscription_id, event_key)
        return {'sent': False, 'reason': 'missing_subscription'}

    if RenewalEmailService.was_notice_sent(subscription, event_key):
        logger.info(
            'Skipping %s email for subscription %s; already sent',
            event_key,
            subscription_id,
        )
        return {'sent': False, 'reason': 'already_sent'}

    sent = RenewalEmailService.send_event_email(
        subscription_id, event_key, subscription=subscription,
    )
    return {'sent': bool(sent)}


@shared_task(bind=True, ignore_result=True, name='billing.tasks.send_expiry_3_day_email')
def send_expiry_3_day_email(self, subscription_id):
    return _send_event_email(subscription_id, 'reminder_3')


@shared_task(bind=True, ignore_result=True, name='billing.tasks.send_expiry_1_day_email')
def send_expiry_1_day_email(self, subscription_id):
    return _send_event_email(subscription_id, 'reminder_1')


@shared_task(bind=True, ignore_result=True, name='billing.tasks.send_expired_email')
def send_expired_email(self, subscription_id):
    return _send_event_email(subscription_id, 'expired')


@shared_task(bind=True, ignore_result=True, name='billing.tasks.send_grace_email')
def send_grace_email(self, subscription_id):
    return _send_event_email(subscription_id, 'grace')


@shared_task(bind=True, ignore_result=True, name='billing.tasks.send_suspended_email')
def send_suspended_email(self, subscription_id):
    return _send_event_email(subscription_id, 'suspended')
