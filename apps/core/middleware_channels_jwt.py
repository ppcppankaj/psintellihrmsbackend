"""
JWT Authentication Middleware for Django Channels (WebSocket)

Replaces session-based AuthMiddlewareStack with JWT token verification.
Extracts JWT from:
  1. Query string: ?token=<jwt>
  2. Sec-WebSocket-Protocol header

On valid JWT, sets scope["user"] to the authenticated user.
On invalid/missing JWT, sets scope["user"] to AnonymousUser.
"""

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)
User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    """
    ASGI middleware that authenticates WebSocket connections via JWT.
    Must be placed BEFORE OrganizationChannelsMiddleware in the stack.
    """

    async def __call__(self, scope, receive, send):
        # Extract token from query string or subprotocol header
        token = self._extract_token(scope)

        if token:
            scope["user"] = await self._authenticate(token)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)

    @staticmethod
    def _extract_token(scope) -> str | None:
        """Extract JWT from query string (?token=xxx) or subprotocol."""
        # 1. Query string
        query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]
        if token:
            return token

        # 2. Sec-WebSocket-Protocol header (Bearer <token>)
        headers = dict(scope.get("headers", []))
        protocols = headers.get(b"sec-websocket-protocol", b"").decode("utf-8", errors="ignore")
        for proto in protocols.split(","):
            proto = proto.strip()
            if proto.startswith("Bearer."):
                return proto[7:]  # After "Bearer."

        return None

    @database_sync_to_async
    def _authenticate(self, raw_token: str):
        """Validate JWT and return the user or AnonymousUser."""
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            access_token = AccessToken(raw_token)
            user_id = access_token.get("user_id")
            if not user_id:
                return AnonymousUser()

            user = User.objects.select_related("organization").get(id=user_id, is_active=True)
            return user
        except User.DoesNotExist:
            logger.warning("ws_jwt_user_not_found token_payload=%s", "redacted")
            return AnonymousUser()
        except Exception as exc:
            logger.warning("ws_jwt_auth_failed error=%s", str(exc))
            return AnonymousUser()
