"""
Organization Safety Guards - Prevent cross-organization data leakage
"""

from django.db import models
from django.db.models import QuerySet
from .context import get_current_organization


class OrganizationQuerySet(QuerySet):
    """
    QuerySet that automatically filters by current organization.
    Prevents cross-organization data leakage.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._organization_filtered = False

    def _filter_by_organization(self):
        if self._organization_filtered:
            return self

        org = get_current_organization()
        if org and hasattr(self.model, 'organization_id'):
            clone = self._clone()
            clone._organization_filtered = True
            return clone.filter(organization_id=org.id)

        self._organization_filtered = True
        return self

    def _clone(self):
        clone = super()._clone()
        clone._organization_filtered = self._organization_filtered
        return clone

    def all(self):
        return super().all()._filter_by_organization()

    def filter(self, *args, **kwargs):
        return super().filter(*args, **kwargs)._filter_by_organization()

    def exclude(self, *args, **kwargs):
        return super().exclude(*args, **kwargs)._filter_by_organization()

    def get(self, *args, **kwargs):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).get(*args, **kwargs)

    def first(self):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).first()

    def last(self):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).last()

    def exists(self):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).exists()

    def count(self):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).count()

    def aggregate(self, *args, **kwargs):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).aggregate(*args, **kwargs)

    def values(self, *fields, **expressions):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).values(*fields, **expressions)

    def values_list(self, *fields, flat=False, named=False):
        qs = self._filter_by_organization()
        return super(OrganizationQuerySet, qs).values_list(
            *fields, flat=flat, named=named
        )

    def unfiltered(self):
        """
        Bypass organization filtering (USE WITH EXTREME CAUTION).
        Only for system-level operations.
        """
        clone = self._clone()
        clone._organization_filtered = True
        return clone


class OrganizationManager(models.Manager):
    """
    Manager that uses OrganizationQuerySet.
    """

    def get_queryset(self):
        return OrganizationQuerySet(self.model, using=self._db)

    def unfiltered(self):
        return self.get_queryset().unfiltered()


class OrganizationSafeModelMixin(models.Model):
    """
    Mixin enforcing organization isolation.
    """

    objects = OrganizationManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if hasattr(self, 'organization_id') and not self.organization_id:
            org = get_current_organization()
            if org:
                self.organization_id = org.id
        super().save(*args, **kwargs)


class OrganizationViewSetMixin:
    """
    ViewSet safety net for organization filtering.
    FAIL-CLOSED: returns empty queryset when no organization context.
    """

    def get_queryset(self):
        queryset = super().get_queryset()

        org = getattr(self.request, 'organization', None) or get_current_organization()

        if not org:
            # FAIL-CLOSED: no organization context → no data
            return queryset.none()

        if hasattr(queryset.model, 'organization_id'):
            queryset = queryset.filter(organization_id=org.id)

        return queryset


def validate_organization_access(obj, request=None):
    """
    Validate object belongs to current organization.
    FAIL-CLOSED: denies access when no org context is available.
    """
    from rest_framework.exceptions import PermissionDenied

    org = get_current_organization()
    if not org:
        raise PermissionDenied(
            "Access denied: no organization context available"
        )

    if hasattr(obj, 'organization_id') and obj.organization_id != org.id:
        raise PermissionDenied(
            "Access denied: resource belongs to different organization"
        )

    return True
