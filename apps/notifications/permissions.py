"""Notification permissions"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class NotificationsTenantPermission(BasePermission):
    """Ensures request is scoped to an organization."""
    message = 'Organization context required for notification operations.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, 'organization', None)
        )

    def has_object_permission(self, request, view, obj):
        organization = getattr(request, 'organization', None)
        if not organization:
            return False
        obj_org = getattr(obj, 'organization_id', None)
        if obj_org is None:
            return True
        return obj_org == organization.id


def _has_org_admin_capability(user) -> bool:
    checker = getattr(user, 'has_permission_for', None)
    if callable(checker) and checker('notifications.manage_notifications'):
        return True
    return getattr(user, 'is_org_admin', False)


class IsNotificationAdmin(BasePermission):
    """Allow HR/Org admins or superusers to manage templates/prefs."""

    required_permission = 'notifications.manage_templates'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if getattr(user, 'is_org_admin', False):
            return True
        checker = getattr(user, 'has_permission_for', None)
        return callable(checker) and checker(self.required_permission)


class IsNotificationManager(BasePermission):
    """Allow broadcast endpoints for authorized managers."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return _has_org_admin_capability(user)
