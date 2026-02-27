"""Utility helpers for chat + meeting features."""

from django.conf import settings
from django.utils.http import urlencode

from apps.core.models import OrganizationDomain


def build_meeting_url(organization, room_id):
    """Constructs absolute meeting link honoring custom domains."""
    if not organization or not room_id:
        return ''

    domain = (
        OrganizationDomain.objects.filter(
            organization=organization,
            is_active=True,
        )
        .order_by('-is_primary')
        .first()
    )

    base_domain = domain.domain_name if domain else getattr(settings, 'BASE_DOMAIN', 'localhost')
    scheme = 'https' if getattr(settings, 'ENVIRONMENT', 'development') == 'production' else 'http'
    return f"{scheme}://{base_domain}/meetings/{room_id}"
