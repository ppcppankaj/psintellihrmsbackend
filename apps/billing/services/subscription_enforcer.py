"""
Subscription Plan Enforcement Engine

Blocks tenant operations that exceed plan limits:
  - max_employees
  - max_branches
  - storage_limit
  - feature flags (payroll_enabled, attendance_enabled, etc.)
"""
import logging
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum

logger = logging.getLogger(__name__)


class SubscriptionLimitExceeded(ValidationError):
    """Raised when a plan capacity limit would be breached."""

    def __init__(self, message, limit_type=None, current=None, maximum=None):
        self.limit_type = limit_type
        self.current = current
        self.maximum = maximum
        super().__init__(message)


class SubscriptionEnforcer:
    """
    Central gate-keeper for plan-based resource limits.

    All checks follow the same contract:
      - Fetch active subscription
      - Compare current usage against the plan ceiling
      - Raise ``SubscriptionLimitExceeded`` if the ceiling is reached
      - Return the subscription on success (enables callers to inspect it)
    """

    # ------------------------------------------------------------------
    # Employee limit
    # ------------------------------------------------------------------
    @classmethod
    def check_employee_limit(cls, organization):
        subscription = cls._require_active(organization)
        max_employees = subscription.plan.max_employees
        if not max_employees:
            return subscription

        from apps.employees.models import Employee

        current = Employee.objects.filter(
            organization=organization,
            is_deleted=False,
        ).count()

        if current >= max_employees:
            raise SubscriptionLimitExceeded(
                f'Employee limit reached ({max_employees}). '
                f'Upgrade your plan to add more employees.',
                limit_type='max_employees',
                current=current,
                maximum=max_employees,
            )
        return subscription

    # ------------------------------------------------------------------
    # Branch limit
    # ------------------------------------------------------------------
    @classmethod
    def check_branch_limit(cls, organization):
        subscription = cls._require_active(organization)
        max_branches = subscription.plan.max_branches
        if not max_branches:
            return subscription

        from apps.authentication.models_hierarchy import Branch

        current = Branch.objects.filter(organization=organization).count()

        if current >= max_branches:
            raise SubscriptionLimitExceeded(
                f'Branch limit reached ({max_branches}). '
                f'Upgrade your plan to add more branches.',
                limit_type='max_branches',
                current=current,
                maximum=max_branches,
            )
        return subscription

    # ------------------------------------------------------------------
    # Storage limit
    # ------------------------------------------------------------------
    @classmethod
    def check_storage_limit(cls, organization, new_file_size):
        subscription = cls._require_active(organization)
        storage_limit_mb = subscription.plan.storage_limit
        if not storage_limit_mb:
            return subscription

        limit_bytes = int(Decimal(storage_limit_mb) * Decimal(1024 * 1024))

        from apps.employees.models import Document
        from apps.onboarding.models import OnboardingDocument

        doc_usage = (
            Document.objects.filter(organization=organization)
            .aggregate(total=Sum('file_size'))
            .get('total') or 0
        )
        onboard_usage = (
            OnboardingDocument.objects.filter(organization=organization)
            .aggregate(total=Sum('file_size'))
            .get('total') or 0
        )
        current_usage = doc_usage + onboard_usage
        projected = current_usage + int(new_file_size or 0)

        if projected > limit_bytes:
            raise SubscriptionLimitExceeded(
                'Storage limit exceeded for your current plan. '
                'Delete unused documents or upgrade your plan.',
                limit_type='storage_limit',
                current=current_usage,
                maximum=limit_bytes,
            )
        return subscription

    # ------------------------------------------------------------------
    # Feature flag
    # ------------------------------------------------------------------
    @classmethod
    def check_feature_flag(cls, organization, feature_flag):
        """
        ``feature_flag`` must match a boolean field on Plan, e.g.
        ``payroll_enabled``, ``attendance_enabled``, ``workflow_enabled``.
        """
        subscription = cls._require_active(organization)
        is_enabled = getattr(subscription.plan, feature_flag, True)
        if not is_enabled:
            raise PermissionDenied(
                'This feature is not available on your current subscription plan.'
            )
        return subscription

    # ------------------------------------------------------------------
    # Usage summary (for dashboard / API)
    # ------------------------------------------------------------------
    @classmethod
    def usage_summary(cls, organization):
        """Return a dict with current usage vs. plan limits."""
        subscription = cls._require_active(organization)
        plan = subscription.plan

        from apps.employees.models import Employee, Document
        from apps.authentication.models_hierarchy import Branch
        from apps.onboarding.models import OnboardingDocument

        employee_count = Employee.objects.filter(
            organization=organization, is_deleted=False
        ).count()
        branch_count = Branch.objects.filter(organization=organization).count()

        doc_usage = (
            Document.objects.filter(organization=organization)
            .aggregate(total=Sum('file_size')).get('total') or 0
        )
        onboard_usage = (
            OnboardingDocument.objects.filter(organization=organization)
            .aggregate(total=Sum('file_size')).get('total') or 0
        )
        storage_used_bytes = doc_usage + onboard_usage

        return {
            'plan_name': plan.name,
            'plan_code': plan.code,
            'employees': {
                'current': employee_count,
                'limit': plan.max_employees,
                'unlimited': plan.max_employees is None,
            },
            'branches': {
                'current': branch_count,
                'limit': plan.max_branches,
                'unlimited': plan.max_branches is None,
            },
            'storage': {
                'used_bytes': storage_used_bytes,
                'used_mb': round(storage_used_bytes / (1024 * 1024), 2) if storage_used_bytes else 0,
                'limit_mb': plan.storage_limit,
                'unlimited': plan.storage_limit is None,
            },
            'features': {
                'payroll': plan.payroll_enabled,
                'recruitment': plan.recruitment_enabled,
                'attendance': plan.attendance_enabled,
                'helpdesk': plan.helpdesk_enabled,
                'timesheet': plan.timesheet_enabled,
                'document': plan.document_enabled,
                'workflow': plan.workflow_enabled,
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @classmethod
    def _require_active(cls, organization):
        from .subscription_service import SubscriptionService
        return SubscriptionService._require_active_subscription(organization)
