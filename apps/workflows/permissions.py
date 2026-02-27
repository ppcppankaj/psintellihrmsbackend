"""Workflow API permissions"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission


def _has_role(user, permission_code: str) -> bool:
    checker = getattr(user, 'has_permission_for', None)
    return bool(callable(checker) and checker(permission_code))


class WorkflowsTenantPermission(BasePermission):
    """Ensures request is scoped to an organization."""
    message = 'Organization context required for workflow operations.'

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


class IsWorkflowAdminOrReadOnly(BasePermission):
    """Read for authenticated users, write for workflow admins."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if user.is_superuser or getattr(user, 'is_org_admin', False):
            return True
        return _has_role(user, 'workflows.manage')


class IsWorkflowManager(BasePermission):
    """Managers who can trigger workflow engine actions."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_org_admin', False):
            return True
        return _has_role(user, 'workflows.manage')


class HasEmployeeProfile(BasePermission):
    """Ensure the user has an employee profile for approvals."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return hasattr(user, 'employee') and user.employee is not None
