"""
Onboarding Signals
SECURITY FIX: Explicit tenant enforcement
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.employees.models import Employee
from .services import OnboardingService


@receiver(post_save, sender=Employee)
def auto_initiate_onboarding(sender, instance, created, **kwargs):
    """
    Optional auto-initiate onboarding.

    🔒 SECURITY:
    - Explicit organization scoping
    """
    if not created:
        return

    if not instance.branch:
        return

    organization = instance.branch.organization
    if not organization:
        return

    # Disabled by default
    # OnboardingService.initiate_onboarding(
    #     employee=instance,
    #     organization_id=organization.id
    # )
