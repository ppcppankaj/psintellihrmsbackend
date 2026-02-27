"""Domain-aware tenant resolution middleware."""

import logging
from typing import Optional

from django.conf import settings
from django.http import JsonResponse


logger = logging.getLogger(__name__)


class DomainTenantMiddleware:
    """Maps incoming hostnames to organizations for white-label domains."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.domain_organization = None
        request.domain_branding = self._default_branding()
        request.domain_email_config = {}

        host = self._extract_host(request)
        domain_entry = self._match_domain(host)

        if domain_entry:
            organization = domain_entry.organization
            if organization and organization.is_active:
                request.domain_organization = organization
                request.organization = organization
                branding, email_settings = self._build_branding(request, organization)
                request.domain_branding = branding
                request.domain_email_config = email_settings

                security_response = self._enforce_domain_security(request, organization)
                if security_response:
                    return security_response

        response = self.get_response(request)
        return response

    def _extract_host(self, request) -> Optional[str]:
        try:
            host = request.get_host()
        except Exception:
            logger.debug("Unable to read host header", exc_info=True)
            return None
        if not host:
            return None
        # Remove port if present
        if ':' in host:
            host = host.split(':', 1)[0]
        return host.lower()

    def _match_domain(self, host):
        if not host:
            return None
        from apps.core.models import OrganizationDomain

        try:
            return (
                OrganizationDomain.objects.select_related('organization')
                .filter(domain_name=host, is_active=True)
                .first()
            )
        except Exception:  # pragma: no cover - defensive DB guard
            logger.exception("Failed to map domain: %s", host)
            return None

    def _build_branding(self, request, organization):
        from apps.core.models import OrganizationSettings

        logo_url = None
        if organization.logo:
            try:
                logo_url = organization.logo.url
                if request and logo_url and not logo_url.startswith('http'):
                    logo_url = request.build_absolute_uri(logo_url)
            except Exception:
                logger.debug("Failed to build logo url for org %s", organization.id, exc_info=True)

        settings_qs = getattr(OrganizationSettings, 'all_objects', OrganizationSettings.objects)
        org_settings = settings_qs.filter(organization=organization).first()

        primary_color = '#1976d2'
        secondary_color = '#dc004e'
        custom_settings = {}
        if org_settings:
            primary_color = org_settings.branding_primary_color or primary_color
            secondary_color = org_settings.branding_secondary_color or secondary_color
            custom_settings = org_settings.custom_settings or {}

        smtp_settings = custom_settings.get('smtp') if isinstance(custom_settings, dict) else {}
        if not isinstance(smtp_settings, dict):
            smtp_settings = {}

        branding = {
            'organization_id': str(organization.id),
            'organization_name': organization.name,
            'logo_url': logo_url,
            'primary_color': primary_color,
            'secondary_color': secondary_color,
            'email': {
                key: value
                for key, value in smtp_settings.items()
                if key in {'from_email', 'reply_to', 'support_email'}
            },
        }
        return branding, smtp_settings

    def _default_branding(self):
        return {
            'organization_id': None,
            'organization_name': getattr(settings, 'DEFAULT_BRAND_NAME', 'PS IntelliHR'),
            'logo_url': getattr(settings, 'DEFAULT_BRAND_LOGO_URL', None),
            'primary_color': getattr(settings, 'DEFAULT_BRAND_PRIMARY_COLOR', '#1976d2'),
            'secondary_color': getattr(settings, 'DEFAULT_BRAND_SECONDARY_COLOR', '#dc004e'),
            'email': {},
        }

    def _enforce_domain_security(self, request, organization):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        domain_org_id = str(organization.id)
        header_org_id = request.headers.get('X-Organization-ID') or request.headers.get('X-Tenant-Id')

        if user.is_superuser:
            if header_org_id and header_org_id != domain_org_id:
                logger.warning(
                    "superuser_domain_mismatch",
                    extra={'event': 'superuser_domain_mismatch', 'user_id': str(user.id), 'domain_org': domain_org_id, 'header_org': header_org_id},
                )
                return JsonResponse(
                    {
                        'error': 'Domain is locked to a specific organization',
                        'code': 'DOMAIN_ENFORCED',
                    },
                    status=403,
                )
            return None

        user_org = getattr(user, 'organization', None)
        if user_org and str(user_org.id) != domain_org_id:
            logger.warning(
                "domain_tenant_violation",
                extra={
                    'event': 'domain_tenant_violation',
                    'user_id': str(user.id),
                    'user_org': str(user_org.id),
                    'domain_org': domain_org_id,
                },
            )
            return JsonResponse(
                {
                    'error': 'This custom domain belongs to another organization',
                    'code': 'DOMAIN_ORG_MISMATCH',
                },
                status=403,
            )
        return None
