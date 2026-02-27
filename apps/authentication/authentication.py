"""
Custom JWT Authentication with Tenant Validation
SECURITY: Validates organization_id claim in JWT matches request organization
"""

import logging
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class OrganizationAwareJWTAuthentication(JWTAuthentication):
    """
    🔒 CRITICAL SECURITY
    - JWT must be tenant-bound
    - Token org must match request org
    - Role context is frozen from token
    """

    def authenticate(self, request):
        result = super().authenticate(request)

        if result is None:
            return None

        user, token = result

        self._validate_org_binding(request, user, token)
        self._attach_role_context(request, token)

        return user, token

    def _validate_org_binding(self, request, user, token):
        """
        Enforce organization isolation
        """
        public_paths = [
            '/api/health/',
            '/api/docs/',
            '/api/redoc/',
        ]

        if any(request.path.startswith(p) for p in public_paths):
            return

        token_org_id = token.get('organization_id')

        # 🔒 Token MUST contain org for non-superusers
        if not token_org_id:
            if user.is_superuser:
                return
            logger.error("JWT rejected: missing organization_id claim")
            raise AuthenticationFailed(_('Organization binding missing in token'))

        request_org = getattr(request, 'organization', None)
        
        # Resolve organization from token if not set by middleware
        # Resolve organization from token if not set by middleware
        if not request_org and token_org_id:
            try:
                from apps.core.models import Organization
                from apps.core.context import set_current_organization
                
                org = Organization.objects.get(id=token_org_id, is_active=True)
                request.organization = org
                set_current_organization(org)
                return
            except Organization.DoesNotExist:
                raise AuthenticationFailed(_('Invalid organization in token'))
            except Exception as e:
                logger.error(f"JWT org resolution failed: {e}")
                raise AuthenticationFailed(_('Organization validation error'))

        if not request_org:
            if user.is_superuser:
                return
            logger.error("JWT rejected: request has no organization context")
            raise AuthenticationFailed(_('Organization context missing'))

        if str(request_org.id) != str(token_org_id):
            logger.error(
                "SECURITY VIOLATION: Cross-tenant token usage",
                extra={
                    'user': user.email,
                    'token_org': token_org_id,
                    'request_org': str(request_org.id),
                }
            )
            raise AuthenticationFailed(
                _('Your credentials do not belong to this organization')
            )

    def _attach_role_context(self, request, token):
        """
        Freeze role context from JWT
        (no DB / header override allowed)
        """
        request.jwt_role_ids = token.get('role_ids', [])


from rest_framework.authentication import SessionAuthentication

class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Disable CSRF checks ONLY for API views that explicitly use this.
    Admin panel remains protected.
    """
    def enforce_csrf(self, request):
        return
