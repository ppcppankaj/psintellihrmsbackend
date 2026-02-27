"""Subscription lifecycle management"""
import logging
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.billing.models import OrganizationSubscription, Plan

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Core subscription helpers: trial provisioning, activation, enforcement."""

    DEFAULT_TRIAL_DAYS = 14
    DEFAULT_PAID_DURATION_DAYS = 30

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------
    @classmethod
    def get_active_subscription(cls, organization):
        """Return the current active subscription or ``None``."""
        if not organization:
            return None
        return (
            OrganizationSubscription.objects.select_related('plan')
            .filter(organization=organization, is_active=True)
            .order_by('-start_date')
            .first()
        )

    @staticmethod
    def get_default_plan():
        """Cheapest active plan used as the free/trial plan."""
        return Plan.objects.filter(is_active=True).order_by('monthly_price').first()

    # ------------------------------------------------------------------
    # Trial management
    # ------------------------------------------------------------------
    @classmethod
    def auto_assign_trial(cls, organization):
        """Provision a 14-day trial for a newly created organization."""
        if OrganizationSubscription.objects.filter(organization=organization).exists():
            return None

        plan = cls.get_default_plan()
        if not plan:
            logger.warning('No active plan found – cannot create trial for %s', organization)
            return None

        start_date = timezone.now().date()
        trial_end = start_date + timedelta(days=cls.DEFAULT_TRIAL_DAYS)
        subscription = OrganizationSubscription.objects.create(
            organization=organization,
            plan=plan,
            start_date=start_date,
            expiry_date=trial_end,
            trial_end_date=trial_end,
            is_trial=True,
            is_active=True,
        )
        logger.info('Trial subscription created for %s (expires %s)', organization, trial_end)
        return subscription

    # ------------------------------------------------------------------
    # Paid activation
    # ------------------------------------------------------------------
    @classmethod
    def activate_paid_subscription(cls, organization, plan, duration_days=None):
        """Deactivate any old subscription and create a paid one."""
        if not organization or not plan:
            raise ValidationError('Organization and plan are required for activation.')

        duration = duration_days or cls.DEFAULT_PAID_DURATION_DAYS
        start_date = timezone.now().date()
        expiry_date = start_date + timedelta(days=duration)

        with db_transaction.atomic():
            active_qs = (
                OrganizationSubscription.objects.select_for_update()
                .filter(organization=organization, is_active=True)
            )
            for sub in active_qs:
                sub.deactivate(reason='replaced_by_payment')

            new_subscription = OrganizationSubscription.objects.create(
                organization=organization,
                plan=plan,
                start_date=start_date,
                expiry_date=expiry_date,
                trial_end_date=None,
                is_trial=False,
                is_active=True,
                grace_period_days=OrganizationSubscription.GRACE_PERIOD_DEFAULT,
            )

        logger.info('Paid subscription activated for %s → plan %s (expires %s)',
                     organization, plan.name, expiry_date)
        return new_subscription

    # ------------------------------------------------------------------
    # Upgrade / downgrade
    # ------------------------------------------------------------------
    @classmethod
    def change_plan(cls, organization, new_plan, duration_days=None):
        """Switch plan for an organization (immediate activation)."""
        old_sub = cls.get_active_subscription(organization)
        remaining_days = 0
        if old_sub and old_sub.expiry_date:
            remaining = (old_sub.expiry_date - timezone.now().date()).days
            remaining_days = max(remaining, 0)

        effective_duration = duration_days or remaining_days or cls.DEFAULT_PAID_DURATION_DAYS
        return cls.activate_paid_subscription(organization, new_plan, effective_duration)

    # ------------------------------------------------------------------
    # Capacity enforcement (delegates to SubscriptionEnforcer)
    # ------------------------------------------------------------------
    @classmethod
    def ensure_employee_capacity(cls, organization):
        from .subscription_enforcer import SubscriptionEnforcer
        return SubscriptionEnforcer.check_employee_limit(organization)

    @classmethod
    def ensure_branch_capacity(cls, organization):
        from .subscription_enforcer import SubscriptionEnforcer
        return SubscriptionEnforcer.check_branch_limit(organization)

    @classmethod
    def ensure_storage_available(cls, organization, new_file_size):
        from .subscription_enforcer import SubscriptionEnforcer
        return SubscriptionEnforcer.check_storage_limit(organization, new_file_size)

    @classmethod
    def ensure_feature_enabled(cls, organization, feature_flag):
        from .subscription_enforcer import SubscriptionEnforcer
        return SubscriptionEnforcer.check_feature_flag(organization, feature_flag)

    # ------------------------------------------------------------------
    # Expiry helpers
    # ------------------------------------------------------------------
    @classmethod
    def deactivate_if_expired(cls, subscription):
        """Deactivate subscription if trial/grace has lapsed. Returns True if deactivated."""
        if not subscription or not subscription.is_active:
            return False
        from .renewal_service import RenewalService

        if subscription.is_trial and subscription.trial_end_date:
            if timezone.now().date() > subscription.trial_end_date:
                subscription.deactivate()
                return True

        if RenewalService.has_grace_passed(subscription):
            subscription.deactivate(reason='grace_period_ended')
            return True

        return False

    @classmethod
    def _require_active_subscription(cls, organization):
        sub = cls.get_active_subscription(organization)
        if not sub:
            raise ValidationError('No active subscription found for this organization.')
        return sub
