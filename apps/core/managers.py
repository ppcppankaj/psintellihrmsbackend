"""
Custom managers for strict query enforcement
Prevents accidental cross-organization data leaks
"""

from django.db import models
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from typing import Optional
import sys

# ============================================================================
# THREAD-LOCAL CONTEXT (USED BY MIDDLEWARE)
# ============================================================================

import threading

_thread_locals = threading.local()


def set_current_branch(branch):
    """
    Set current branch in thread-local storage
    Used by middleware
    """
    _thread_locals.current_branch = branch


def get_current_branch() -> Optional[object]:
    """
    Get current branch from thread-local storage
    Returns None if not set
    """
    return getattr(_thread_locals, 'current_branch', None)


def set_current_organization(organization):
    """
    Set current organization in thread-local storage
    Used by middleware
    """
    _thread_locals.current_organization = organization


def get_current_organization() -> Optional[object]:
    """
    Get current organization from thread-local storage
    Returns None if not set
    """
    return getattr(_thread_locals, 'current_organization', None)


def clear_thread_locals():
    """
    Clear all thread-local variables
    """
    for attr in ['current_branch', 'current_organization']:
        if hasattr(_thread_locals, attr):
            delattr(_thread_locals, attr)


# ============================================================================
# ORG + BRANCH QUERYSET
# ============================================================================

class OrgBranchQuerySet(models.QuerySet):
    """QuerySet with automatic branch filtering"""

    def _require_org(self):
        org = get_current_organization()
        if not org:
            raise PermissionDenied(
                "Organization context not set. "
                "Ensure OrganizationMiddleware is enabled."
            )
        return org

    def for_request(self, request):
        """
        Filter queryset by user's accessible branches

        Args:
            request: Django request object with authenticated user

        Returns:
            Filtered queryset
        """
        # Superuser bypass
        if request.user.is_superuser:
            return self

        org = self._require_org()

        from apps.authentication.models_hierarchy import BranchUser

        branch_ids = list(
            BranchUser.objects.filter(
                user=request.user,
                is_active=True,
                branch__organization=org
            ).values_list('branch_id', flat=True)
        )

        if not branch_ids:
            return self.none()

        return self.filter(
            branch_id__in=branch_ids,
            branch__organization=org
        )

    def for_organization(self, organization):
        """
        Filter queryset by organization
        """
        org_id = organization.id if hasattr(organization, 'id') else organization
        return self.filter(branch__organization_id=org_id)

    def for_branch(self, branch):
        """
        Filter queryset by specific branch
        """
        branch_id = branch.id if hasattr(branch, 'id') else branch
        return self.filter(branch_id=branch_id)

    def for_branches(self, branches):
        """
        Filter queryset by multiple branches
        """
        if branches and hasattr(branches[0], 'id'):
            branch_ids = [b.id for b in branches]
        else:
            branch_ids = branches
        return self.filter(branch_id__in=branch_ids)


class OrgBranchManager(models.Manager):
    """
    Manager that enforces branch-level filtering

    Usage in models:
        class Employee(models.Model):
            objects = OrgBranchManager()
    """

    def get_queryset(self):
        """
        HARD ENFORCEMENT:
        Always scope by current organization
        """
        qs = OrgBranchQuerySet(self.model, using=self._db)

        # Bypass for management commands (migrations, shell, etc.)
        COMMANDS_TO_SKIP = [
            'migrate', 'makemigrations', 'shell', 'createsuperuser',
            'collectstatic', 'check', 'loaddata', 'dumpdata', 'test'
        ]
        if len(sys.argv) > 1 and sys.argv[1] in COMMANDS_TO_SKIP:
            return qs

        org = get_current_organization()
        if not org:
            raise PermissionDenied(
                "Organization context missing for branch-scoped model"
            )

        return qs.filter(branch__organization=org)

    # Explicit escape hatch for admin / migrations ONLY
    def unsafe_all(self):
        return super().get_queryset()

    def for_request(self, request):
        return self.get_queryset().for_request(request)

    def for_organization(self, organization):
        return self.get_queryset().for_organization(organization)

    def for_branch(self, branch):
        return self.get_queryset().for_branch(branch)

    def for_branches(self, branches):
        return self.get_queryset().for_branches(branches)


# ============================================================================
# ORGANIZATION-ONLY QUERYSET
# ============================================================================

class OrganizationScopedQuerySet(models.QuerySet):
    """QuerySet for organization-level models (no branch)"""

    def _require_org(self):
        org = get_current_organization()
        if not org:
            raise PermissionDenied(
                "Organization context not set. "
                "Ensure OrganizationMiddleware is enabled."
            )
        return org

    def for_request(self, request):
        """Filter by user's organization"""
        if request.user.is_superuser:
            return self

        org = self._require_org()
        return self.filter(organization=org)

    def for_organization(self, organization):
        """Filter by specific organization"""
        org_id = organization.id if hasattr(organization, 'id') else organization
        return self.filter(organization_id=org_id)


class OrganizationScopedManager(models.Manager):
    """
    Manager for organization-scoped models

    Usage:
        class Department(models.Model):
            objects = OrganizationScopedManager()
    """

    def get_queryset(self):
        """
        HARD ENFORCEMENT:
        Always scope by current organization
        """
        qs = OrganizationScopedQuerySet(self.model, using=self._db)

        # Bypass for management commands
        COMMANDS_TO_SKIP = [
            'migrate', 'makemigrations', 'shell', 'createsuperuser',
            'collectstatic', 'check', 'loaddata', 'dumpdata', 'test'
        ]
        if len(sys.argv) > 1 and sys.argv[1] in COMMANDS_TO_SKIP:
            return qs

        org = get_current_organization()
        if not org:
            raise PermissionDenied(
                "Organization context missing for organization-scoped model"
            )

        return qs.filter(organization=org)

    # Explicit escape hatch
    def unsafe_all(self):
        return super().get_queryset()

    def for_request(self, request):
        return self.get_queryset().for_request(request)

    def for_organization(self, organization):
        return self.get_queryset().for_organization(organization)
