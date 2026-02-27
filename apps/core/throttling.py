"""
Central DRF throttle classes used across environments.

Rates are controlled from `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from django.core.cache import cache
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle


def _ident(request: Request) -> str:
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "unknown")


def _safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class OrganizationRateThrottle(SimpleRateThrottle):
    scope = "organization"

    def get_cache_key(self, request: Request, view=None) -> Optional[str]:
        org = getattr(request, "organization", None)
        if org:
            return f"throttle:org:{org.id}"
        return f"throttle:org:ip:{_ident(request)}"


class OrganizationUserRateThrottle(SimpleRateThrottle):
    scope = "org_user"

    def get_cache_key(self, request: Request, view=None) -> Optional[str]:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        org = getattr(request, "organization", None)
        org_id = getattr(org, "id", getattr(user, "organization_id", "global"))
        return f"throttle:org:{org_id}:user:{user.id}"


class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request: Request, view=None) -> str:
        email = str(request.data.get("email", "")).strip().lower()
        email_key = _safe_hash(email) if email else "no-email"
        return f"throttle:login:{_ident(request)}:{email_key}"


class TwoFactorRateThrottle(SimpleRateThrottle):
    scope = "two_factor"

    def get_cache_key(self, request: Request, view=None) -> str:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"throttle:2fa:user:{user.id}"
        return f"throttle:2fa:ip:{_ident(request)}"


class PasswordResetThrottle(SimpleRateThrottle):
    scope = "password_reset"

    def get_cache_key(self, request: Request, view=None) -> str:
        email = str(request.data.get("email", "")).strip().lower()
        email_key = _safe_hash(email) if email else "no-email"
        return f"throttle:password_reset:{_ident(request)}:{email_key}"


class AttendancePunchThrottle(SimpleRateThrottle):
    scope = "attendance_punch"

    def get_cache_key(self, request: Request, view=None) -> str:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"throttle:attendance_punch:user:{user.id}"
        return f"throttle:attendance_punch:ip:{_ident(request)}"


class APIKeyRateThrottle(SimpleRateThrottle):
    scope = "api_key"

    def get_cache_key(self, request: Request, view=None) -> Optional[str]:
        api_key = request.META.get("HTTP_X_API_KEY")
        if not api_key:
            return None
        return f"throttle:api_key:{_safe_hash(api_key)}"


class BurstRateThrottle(SimpleRateThrottle):
    scope = "burst"

    def get_cache_key(self, request: Request, view=None) -> str:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"throttle:burst:user:{user.id}"
        return f"throttle:burst:ip:{_ident(request)}"


class SustainedRateThrottle(SimpleRateThrottle):
    scope = "sustained"

    def get_cache_key(self, request: Request, view=None) -> str:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"throttle:sustained:user:{user.id}"
        return f"throttle:sustained:ip:{_ident(request)}"


class ReportExportThrottle(SimpleRateThrottle):
    scope = "report_export"

    def get_cache_key(self, request: Request, view=None) -> str:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"throttle:report_export:user:{user.id}"
        return f"throttle:report_export:ip:{_ident(request)}"


# Backward-compatible aliases
LoginThrottle = LoginRateThrottle
ExportThrottle = ReportExportThrottle


def is_tenant_rate_limited(organization_id: str, threshold: int = 10000) -> bool:
    key = f"throttle:tenant:{organization_id}"
    return cache.get(key, 0) > threshold


def get_tenant_request_count(organization_id: str) -> int:
    return cache.get(f"throttle:tenant:{organization_id}", 0)


def get_user_request_count(user_id: str) -> int:
    return cache.get(f"throttle:burst:user:{user_id}", 0)


def block_ip(ip_address: str, duration_seconds: int = 3600) -> None:
    cache.set(f"blocked:ip:{ip_address}", True, duration_seconds)


def is_ip_blocked(ip_address: str) -> bool:
    return bool(cache.get(f"blocked:ip:{ip_address}", False))


def unblock_ip(ip_address: str) -> None:
    cache.delete(f"blocked:ip:{ip_address}")


THROTTLE_CLASSES_BY_ENDPOINT: dict[str, list[type[SimpleRateThrottle]]] = {
    "login": [LoginRateThrottle, BurstRateThrottle],
    "password_reset": [PasswordResetThrottle, BurstRateThrottle],
    "two_factor": [TwoFactorRateThrottle, BurstRateThrottle],
    "attendance_punch": [AttendancePunchThrottle, OrganizationUserRateThrottle],
    "api": [
        OrganizationRateThrottle,
        OrganizationUserRateThrottle,
        BurstRateThrottle,
        SustainedRateThrottle,
    ],
    "report_export": [ReportExportThrottle, OrganizationUserRateThrottle],
}
