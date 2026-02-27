"""Authentication signals for tenant safety."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .models_hierarchy import OrganizationUser


@receiver(post_save, sender=User)
def auto_create_organization_user(sender, instance: User, created: bool, **kwargs):
    """Ensure every user gets an OrganizationUser record when an organization is assigned."""
    if not created:
        return

    organization_id = instance.organization_id
    if not organization_id:
        return

    try:
        from apps.core.models import Organization
        organization = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        return

    OrganizationUser.objects.get_or_create(
        user=instance,
        organization=organization,
        defaults={
            'role': OrganizationUser.RoleChoices.ORG_ADMIN if instance.is_org_admin else OrganizationUser.RoleChoices.EMPLOYEE,
            'is_active': True,
            'created_by': None,
        },
    )
