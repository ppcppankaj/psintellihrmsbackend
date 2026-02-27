"""
Celery task: subscription_expiry_task

Runs daily via Celery Beat.
Handles:
  - Trial expiry
  - Subscription expiry reminders (3 days, 1 day)
  - Grace period enforcement
  - Organization suspension
  - Organization status sync
"""
import logging

from celery import shared_task
from django.utils import timezone

from apps.billing.models import OrganizationSubscription

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True, name='billing.tasks.subscription_expiry_task')
def subscription_expiry_task(self):
    """
    Daily sweep of all active subscriptions.

    For each subscription the task:
      1. Checks trial expiry → deactivate if past ``trial_end_date``
      2. Delegates to ``RenewalService.process_subscription`` for reminder
         emails, grace-period tracking, and final suspension.
      3. Syncs ``organization.subscription_status`` to match the lifecycle
         stage (trial → active → past_due → suspended).
    """
    from apps.billing.services import RenewalService, SubscriptionService

    today = timezone.now().date()
    logger.info('[subscription_expiry_task] Running for %s', today)

    active_subs = (
        OrganizationSubscription.objects
        .select_related('organization', 'plan')
        .filter(is_active=True)
    )

    stats = {
        'date': str(today),
        'processed': 0,
        'trials_expired': 0,
        'reminders_sent': 0,
        'grace_entered': 0,
        'suspended': 0,
    }

    for subscription in active_subs.iterator():
        if not subscription.expiry_date:
            continue

        stats['processed'] += 1

        # -- Trial expiry check --
        if subscription.is_trial and subscription.trial_end_date:
            if today > subscription.trial_end_date:
                subscription.deactivate(reason='trial_expired')
                stats['trials_expired'] += 1
                logger.info('Trial expired for org %s', subscription.organization_id)
                continue

        # -- Renewal lifecycle (reminders → grace → suspend) --
        events = RenewalService.process_subscription(subscription)
        if events.get('reminder_3') or events.get('reminder_1'):
            stats['reminders_sent'] += 1
        if events.get('grace'):
            stats['grace_entered'] += 1
        if events.get('suspended'):
            stats['suspended'] += 1

    logger.info('[subscription_expiry_task] Complete: %s', stats)
    return stats
