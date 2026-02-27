"""JWT middleware enforcing domain-bound organization claims."""
import logging

from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)
DOMAIN_MISMATCH_STATUS = 4403


class JWTDomainEnforcementMiddleware:
    """Compare token organization claim to request/domain organization context."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.authenticator = JWTAuthentication()

    def __call__(self, request):
        response = self._enforce(request)
        if response:
            return response
        return self.get_response(request)

    def _enforce(self, request):
        org_context = getattr(request, 'organization', None) or getattr(request, 'domain_organization', None)
        if not org_context:
            return None

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header or not auth_header.lower().startswith('bearer '):
            return None

        raw_token = auth_header.split(' ', 1)[1].strip()
        if not raw_token:
            return None

        try:
            token = self.authenticator.get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            logger.debug('JWTDomainEnforcementMiddleware: token invalid, skipping enforcement')
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning('JWTDomainEnforcementMiddleware failed to decode token: %s', exc)
            return None

        token_org_id = token.get('organization_id')
        if not token_org_id:
            return None

        if str(token_org_id) != str(org_context.id):
            logger.warning(
                'domain_mismatch_block',
                extra={
                    'event': 'domain_mismatch_block',
                    'token_org': token_org_id,
                    'request_org': str(org_context.id),
                    'path': request.path,
                },
            )
            return JsonResponse(
                {
                    'error': 'Domain is locked to another organization',
                    'code': 'DOMAIN_MISMATCH',
                },
                status=DOMAIN_MISMATCH_STATUS,
            )

        return None
