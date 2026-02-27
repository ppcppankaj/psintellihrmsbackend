"""
Signal handlers for subscription automation.

🔒 SECURITY:
 - Trial auto-provisioned on Organization creation
 - Plan limits enforced on Employee / Branch / Document pre_save
 - All guards delegate to SubscriptionEnforcer for single source of truth
"""
import logging

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.authentication.models_hierarchy import Branch
from apps.core.models import Organization
from apps.employees.models import Document, Employee

from .services import SubscriptionService, SubscriptionEnforcer

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 1. Auto-create trial subscription when a new Organization is saved
# ------------------------------------------------------------------
@receiver(post_save, sender=Organization)
def ensure_trial_subscription(sender, instance, created, **kwargs):
    """Provision a 14-day trial for every newly created organization."""
    if created:
        try:
            SubscriptionService.auto_assign_trial(instance)
        except Exception:
            logger.exception('Failed to create trial subscription for %s', instance)


# ------------------------------------------------------------------
# 2. Employee capacity guard
# ------------------------------------------------------------------
@receiver(pre_save, sender=Employee)
def enforce_employee_plan_limit(sender, instance, **kwargs):
    """Block new employee creation when plan limit is reached."""
    if instance.pk or not instance.organization_id:
        return
    SubscriptionEnforcer.check_employee_limit(instance.organization)


# ------------------------------------------------------------------
# 3. Branch capacity guard
# ------------------------------------------------------------------
@receiver(pre_save, sender=Branch)
def enforce_branch_plan_limit(sender, instance, **kwargs):
    """Block new branch creation when plan limit is reached."""
    if instance.pk or not instance.organization_id:
        return
    SubscriptionEnforcer.check_branch_limit(instance.organization)


# ------------------------------------------------------------------
# 4. Storage capacity guard
# ------------------------------------------------------------------
@receiver(pre_save, sender=Document)
def enforce_storage_limit(sender, instance, **kwargs):
    """Block document upload when storage quota is exceeded."""
    if not instance.organization_id:
        return

    new_file = getattr(instance, 'file', None)
    file_size = getattr(new_file, 'size', None) or instance.file_size or 0

    if instance.pk:
        try:
            previous_size = (
                Document.objects.filter(pk=instance.pk)
                .values_list('file_size', flat=True)
                .first() or 0
            )
        except Document.DoesNotExist:
            previous_size = 0
        delta = max(file_size - previous_size, 0)
    else:
        delta = file_size

    if delta <= 0:
        return

    SubscriptionEnforcer.check_storage_limit(instance.organization, delta)
    instance.file_size = file_size