"""
Base Celery Tasks
SECURITY: Enforces tenant isolation for background jobs
"""

from celery import shared_task
from apps.core.models import Organization


class TenantTaskError(Exception):
    pass


class TenantAwareTask:
    """
    Base mixin for tenant-safe Celery tasks
    """

    @staticmethod
    def get_organization(organization_id):
        if not organization_id:
            raise TenantTaskError("organization_id is required")

        try:
            return Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise TenantTaskError(f"Invalid organization_id: {organization_id}")
