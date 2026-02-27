"""
Organization Middleware - Production Ready Multi-Tenancy Implementation

CRITICAL:
- Async-safe (contextvars)
- Migration-safe
- Oracle VM / Docker safe
- PostgreSQL RLS compatible
- drf-spectacular schema-safe
"""

import sys
import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

# =============================================================================
# Utilities
# =============================================================================

COMMANDS_TO_SKIP = {
    "makemigrations",
    "migrate",
    "shell",
    "createsuperuser",
    "collectstatic",
    "check",
    "loaddata",
    "dumpdata",
    "flush",
    "test",
}


def is_management_command() -> bool:
    return any(cmd in sys.argv for cmd in COMMANDS_TO_SKIP)


def is_public_path(path: str) -> bool:
    """
    Public paths that MUST bypass tenant enforcement.
    """
    PUBLIC_PATHS = (
        "/api/schema",
        "/api/docs",
        "/api/redoc",
        "/api/health",
        "/admin",
        "/static",
        "/media",
    )
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PATHS)


def log_superuser_org_switch(user, organization, request=None):
    logger.warning(
        "superuser_org_switch",
        extra={
            "event": "superuser_org_switch",
            "user_id": str(user.id),
            "user_email": user.email,
            "organization_id": str(organization.id),
            "organization_name": organization.name,
            "ip_address": request.META.get("REMOTE_ADDR") if request else None,
        },
    )


# =============================================================================
# Middleware
# =============================================================================

class OrganizationMiddleware(MiddlewareMixin):
    """
    Resolves and enforces organization context.

    MUST run AFTER AuthenticationMiddleware.
    """

    def process_request(self, request):
        from apps.core.context import (
            set_current_organization,
            set_current_user,
            clear_context,
        )

        # ---------------------------------------------------------------------
        # Always start clean (async-safe)
        # ---------------------------------------------------------------------
        clear_context()
        request.organization = None

        # ---------------------------------------------------------------------
        # HARD SKIP: OpenAPI / Swagger schema (CRITICAL)
        # ---------------------------------------------------------------------
        if request.path.startswith("/api/schema"):
            logger.debug("OrganizationMiddleware skipped for schema path")
            return None

        # ---------------------------------------------------------------------
        # Skip management commands
        # ---------------------------------------------------------------------
        if is_management_command():
            logger.debug("OrganizationMiddleware skipped for management command")
            return None

        # ---------------------------------------------------------------------
        # Skip drf-spectacular fake schema view
        # ---------------------------------------------------------------------
        if getattr(request, "swagger_fake_view", False):
            logger.debug("OrganizationMiddleware skipped swagger_fake_view")
            return None

        # ---------------------------------------------------------------------
        # Skip public paths
        # ---------------------------------------------------------------------
        if is_public_path(request.path):
            logger.debug(
                "OrganizationMiddleware skipped public path: %s",
                request.path,
            )
            return None

        # ---------------------------------------------------------------------
        # Skip unauthenticated users
        # ---------------------------------------------------------------------
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            logger.debug("OrganizationMiddleware unauthenticated request")
            return None

        # ---------------------------------------------------------------------
        # Set user context
        # ---------------------------------------------------------------------
        set_current_user(request.user)
        logger.debug("Authenticated user: %s", request.user.email)

        from apps.core.models import Organization

        # ---------------------------------------------------------------------
        # User has organization
        # S6 — HEADER SPOOFING PROTECTION: Non-superusers ALWAYS use their
        # own organization. X-Organization-ID header is IGNORED for them.
        # ---------------------------------------------------------------------
        if getattr(request.user, "organization", None):
            org = request.user.organization

            # S6: Detect and log header spoofing attempts by non-superusers
            if not request.user.is_superuser:
                spoofed_org_id = (
                    request.headers.get("X-Organization-ID")
                    or request.headers.get("X-Tenant-Id")
                )
                if spoofed_org_id and str(spoofed_org_id) != str(org.id):
                    logger.warning(
                        "header_spoofing_blocked",
                        extra={
                            "event": "header_spoofing_blocked",
                            "user_id": str(request.user.id),
                            "user_email": request.user.email,
                            "user_org_id": str(org.id),
                            "spoofed_org_id": spoofed_org_id,
                            "ip_address": request.META.get("REMOTE_ADDR"),
                        },
                    )
                    return JsonResponse(
                        {
                            "error": "Organization header spoofing detected",
                            "code": "HEADER_SPOOFING",
                        },
                        status=403,
                    )

            domain_org = getattr(request, 'domain_organization', None)
            if (
                domain_org
                and not request.user.is_superuser
                and org.id != domain_org.id
            ):
                logger.warning(
                    "domain_mismatch_block",
                    extra={
                        "event": "domain_mismatch_block",
                        "user_id": str(request.user.id),
                        "user_org": str(org.id),
                        "domain_org": str(domain_org.id),
                    },
                )
                return JsonResponse(
                    {
                        "error": "Domain is tied to another organization",
                        "code": "DOMAIN_MISMATCH",
                    },
                    status=403,
                )

            if not org.is_active:
                logger.warning(
                    "inactive_organization_access",
                    extra={
                        "event": "inactive_organization_access",
                        "user_id": str(request.user.id),
                        "organization_id": str(org.id),
                    },
                )
                return JsonResponse(
                    {"error": "Organization is inactive", "code": "ORG_INACTIVE"},
                    status=403,
                )

            if org.subscription_status in {"suspended", "cancelled"}:
                logger.warning(
                    "inactive_subscription_access",
                    extra={
                        "event": "inactive_subscription_access",
                        "user_id": str(request.user.id),
                        "organization_id": str(org.id),
                        "subscription_status": org.subscription_status,
                    },
                )
                return JsonResponse(
                    {
                        "error": "Organization subscription inactive",
                        "subscription_status": org.subscription_status,
                        "code": "SUBSCRIPTION_INACTIVE",
                    },
                    status=403,
                )

            set_current_organization(org)
            request.organization = org

            # PostgreSQL RLS support
            if getattr(settings, "ENABLE_POSTGRESQL_RLS", False):
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SET LOCAL app.current_organization_id = %s",
                            [str(org.id)],
                        )
                except Exception:
                    logger.exception("Failed to set PostgreSQL RLS context")

            return None

        # ---------------------------------------------------------------------
        # Superuser without organization
        # ---------------------------------------------------------------------
        if request.user.is_superuser:
            domain_org = getattr(request, 'domain_organization', None)
            header_org_id = (
                request.headers.get("X-Organization-ID")
                or request.headers.get("X-Tenant-Id")
            )

            if domain_org:
                domain_org_id = str(domain_org.id)
                if header_org_id and header_org_id != domain_org_id:
                    logger.warning(
                        "superuser_domain_override_block",
                        extra={
                            "event": "superuser_domain_override_block",
                            "user_id": str(request.user.id),
                            "header_org": header_org_id,
                            "domain_org": domain_org_id,
                        },
                    )
                    return JsonResponse(
                        {
                            "error": "Domain is locked to a specific organization",
                            "code": "DOMAIN_ENFORCED",
                        },
                        status=403,
                    )

                set_current_organization(domain_org)
                request.organization = domain_org

                if getattr(settings, "ENABLE_POSTGRESQL_RLS", False):
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SET LOCAL app.current_organization_id = %s",
                                [str(domain_org.id)],
                            )
                    except Exception:
                        logger.exception("Failed to set RLS for domain-bound superuser")

                return None

            org_id = header_org_id

            if org_id:
                try:
                    org = Organization.objects.get(id=org_id, is_active=True)

                    log_superuser_org_switch(request.user, org, request)

                    set_current_organization(org)
                    request.organization = org

                    if getattr(settings, "ENABLE_POSTGRESQL_RLS", False):
                        try:
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    "SET LOCAL app.current_organization_id = %s",
                                    [str(org.id)],
                                )
                        except Exception:
                            logger.exception("Failed to set RLS for superuser")

                except Organization.DoesNotExist:
                    logger.warning(
                        "invalid_org_switch",
                        extra={
                            "event": "invalid_org_switch",
                            "user_id": str(request.user.id),
                            "organization_id": org_id,
                        },
                    )
                    return JsonResponse(
                        {"error": "Invalid organization ID", "code": "INVALID_ORG"},
                        status=400,
                    )

            # Superuser allowed without org
            return None

        # ---------------------------------------------------------------------
        # Regular user without organization (BLOCK)
        # ---------------------------------------------------------------------
        logger.warning(
            "user_without_organization",
            extra={
                "event": "user_without_organization",
                "user_id": str(request.user.id),
            },
        )
        return JsonResponse(
            {"error": "User has no organization", "code": "NO_ORG"},
            status=403,
        )

    # -------------------------------------------------------------------------
    # Cleanup (async-safe)
    # -------------------------------------------------------------------------

    def process_response(self, request, response):
        from apps.core.context import clear_context
        clear_context()
        return response

    def process_exception(self, request, exception):
        from apps.core.context import clear_context
        clear_context()
        return None
