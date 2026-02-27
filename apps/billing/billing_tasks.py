"""Celery tasks for billing and renewals."""
import logging

from celery import shared_task
from django.utils import timezone

from .models import OrganizationSubscription
from .billing_services import RenewalEmailService, RenewalService


logger = logging.getLogger(__name__)


def _load_subscription(subscription_id):
    return (
        OrganizationSubscription.objects.select_related('organization', 'plan')
        .filter(id=subscription_id)
        .first()
    )


def _send_event_email(subscription_id, event_key):
    subscription = _load_subscription(subscription_id)
    if not subscription:
        logger.warning('Subscription %s not found for %s email', subscription_id, event_key)
        return {'sent': False, 'reason': 'missing_subscription'}

    if RenewalEmailService.was_notice_sent(subscription, event_key):
        logger.info('Skipping %s email for subscription %s; already sent', event_key, subscription_id)
        return {'sent': False, 'reason': 'already_sent'}

    sent = RenewalEmailService.send_event_email(subscription_id, event_key, subscription=subscription)
    return {'sent': bool(sent)}


@shared_task(bind=True, ignore_result=True, name="billing.tasks.send_expiry_3_day_email")
def send_expiry_3_day_email(self, subscription_id):
    return _send_event_email(subscription_id, 'reminder_3')


@shared_task(bind=True, ignore_result=True, name="billing.tasks.send_expiry_1_day_email")
def send_expiry_1_day_email(self, subscription_id):
    return _send_event_email(subscription_id, 'reminder_1')


@shared_task(bind=True, ignore_result=True, name="billing.tasks.send_expired_email")
def send_expired_email(self, subscription_id):
    return _send_event_email(subscription_id, 'expired')


@shared_task(bind=True, ignore_result=True, name="billing.tasks.send_grace_email")
def send_grace_email(self, subscription_id):
    return _send_event_email(subscription_id, 'grace')


@shared_task(bind=True, ignore_result=True, name="billing.tasks.send_suspended_email")
def send_suspended_email(self, subscription_id):
    return _send_event_email(subscription_id, 'suspended')


@shared_task(bind=True, ignore_result=True, name="billing.tasks.check_subscription_expiry")
def check_subscription_expiry(self):
    """Daily job to send renewal reminders and enforce grace logic."""
    today = timezone.now().date()
    subscriptions = (
        OrganizationSubscription.objects.select_related('organization', 'plan')
        .filter(is_active=True)
    )
    processed = 0
    for subscription in subscriptions:
        if not subscription.expiry_date:
            continue
        RenewalService.process_subscription(subscription)
        processed += 1
    return {'date': str(today), 'processed': processed}


# Backward compatibility for any legacy references
process_subscription_expiry_reminders = check_subscription_expiry
