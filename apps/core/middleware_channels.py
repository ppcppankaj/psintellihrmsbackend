"""
Organization Channels Middleware - Multi-Tenancy for WebSockets
Resolves organization context for ASGI/Channels connections.
"""

import logging
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from apps.core.context import set_current_organization, set_current_user, clear_context

logger = logging.getLogger(__name__)

class OrganizationChannelsMiddleware(BaseMiddleware):
    """
    Middleware to resolve organization context for WebSocket connections.
    Should be wrapped around AuthMiddlewareStack.
    """

    async def __call__(self, scope, receive, send):
        # Start clean
        clear_context()
        
        user = scope.get('user')
        if not user or not user.is_authenticated:
            return await super().__call__(scope, receive, send)

        # Set user context (async-safe via contextvars)
        set_current_user(user)

        host = self._extract_host(scope)
        domain_org = None
        if host:
            domain_org = await self.get_domain_organization(host)
            if domain_org:
                scope['domain_organization'] = domain_org

        user_org = await self.get_organization(user)
        resolved_org = None

        if domain_org and user_org and domain_org.id != user_org.id:
            scope['org_mismatch'] = True
            logger.warning(
                "channels_domain_user_mismatch",
                extra={
                    "event": "channels_domain_user_mismatch",
                    "user_id": str(user.id),
                    "domain_org": str(domain_org.id),
                    "user_org": str(user_org.id),
                },
            )
        else:
            resolved_org = domain_org or user_org

        if resolved_org:
            scope['organization'] = resolved_org
            set_current_organization(resolved_org)
            logger.debug("WebSocket context set for Org: %s", resolved_org.name)
        
        try:
            return await super().__call__(scope, receive, send)
        finally:
            # Cleanup
            clear_context()

    @database_sync_to_async
    def get_organization(self, user):
        """
        Database lookup for user's organization.
        """
        try:
            if hasattr(user, 'organization') and user.organization:
                return user.organization
            
            # Fallback for superusers if needed, though they usually 
            # don't have a default org.
            return None
        except Exception as e:
            logger.error(f"Error resolving organization for WebSocket: {e}")
            return None

    def _extract_host(self, scope):
        headers = dict(scope.get('headers', []))
        host = headers.get(b'host')
        if not host:
            return None
        host = host.decode().split(':', 1)[0].strip().lower()
        return host or None

    @database_sync_to_async
    def get_domain_organization(self, host):
        if not host:
            return None
        try:
            from apps.core.models import OrganizationDomain

            domain = (
                OrganizationDomain.objects.select_related('organization')
                .filter(domain_name=host, is_active=True)
                .first()
            )
            return domain.organization if domain else None
        except Exception as exc:
            logger.error("Error resolving domain %s for WebSocket: %s", host, exc)
            return None
