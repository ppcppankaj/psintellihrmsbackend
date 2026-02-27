"""
PostgreSQL Row-Level Security Context Middleware
=================================================

Sets TWO PostgreSQL session variables on every request:

    SET LOCAL app.current_organization_id = '<uuid>';
    SET LOCAL app.current_is_superuser    = 'true' | 'false';

``SET LOCAL`` scopes variables to the current transaction.
Combined with ``ATOMIC_REQUESTS = True`` this guarantees:
  • No context leakage across requests (Gunicorn / PgBouncer safe)
  • Automatic cleanup at transaction boundary
  • RLS policies see correct tenant for every query

This middleware MUST run immediately AFTER ``OrganizationMiddleware``
so that ``request.organization`` is already resolved.

If ``ENABLE_POSTGRESQL_RLS`` is ``False`` the middleware is a no-op.
"""

import logging

from django.conf import settings
from django.db import connection
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Null UUID used when no organisation context is available.
# RLS policies will match zero rows against this sentinel,
# providing fail-closed behaviour.
_NULL_ORG = "00000000-0000-0000-0000-000000000000"


class RLSContextMiddleware(MiddlewareMixin):
    """
    Inject tenant context into the PostgreSQL session for RLS enforcement.

    Placement in ``MIDDLEWARE`` (settings):
        ... after OrganizationMiddleware ...
        "apps.core.middleware_rls.RLSContextMiddleware",
        ... before SubscriptionMiddleware ...
    """

    # ── Guard flags ──────────────────────────────────────────────────────
    _enabled = None  # Lazy-evaluated once

    @classmethod
    def _is_enabled(cls):
        if cls._enabled is None:
            cls._enabled = (
                getattr(settings, "ENABLE_POSTGRESQL_RLS", False)
                and connection.vendor == "postgresql"
            )
        return cls._enabled

    # ── Request handling ─────────────────────────────────────────────────

    def process_request(self, request):
        if not self._is_enabled():
            return None

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            # Unauthenticated → fail-closed (null org, non-super)
            self._set_rls_context(_NULL_ORG, "false")
            return None

        # Resolve organisation
        org = getattr(request, "organization", None)
        org_id = str(org.id) if org else _NULL_ORG

        # Resolve superuser flag
        is_super = "true" if user.is_superuser else "false"

        self._set_rls_context(org_id, is_super)
        return None

    # ── Response handling (belt & suspenders cleanup) ────────────────────

    def process_response(self, request, response):
        if self._is_enabled():
            self._reset_rls_context()
        return response

    def process_exception(self, request, exception):
        if self._is_enabled():
            self._reset_rls_context()
        return None

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _set_rls_context(org_id: str, is_superuser: str):
        """
        SET LOCAL scopes the variable to the current transaction.
        If ATOMIC_REQUESTS is True every view runs inside a transaction,
        so the variable is automatically cleared at transaction end.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET LOCAL app.current_organization_id = %s;", [org_id]
                )
                cursor.execute(
                    "SET LOCAL app.current_is_superuser = %s;", [is_superuser]
                )
        except Exception:
            logger.exception("rls_context_set_failed")

    @staticmethod
    def _reset_rls_context():
        """
        Explicit RESET as safety net — even though SET LOCAL expires at
        transaction boundary, PgBouncer in statement-mode could leak
        session state without this.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_organization_id;")
                cursor.execute("RESET app.current_is_superuser;")
        except Exception:
            # Connection may already be closed / returned to pool
            pass
