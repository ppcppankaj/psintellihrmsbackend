"""
Core Models - Base classes for all HRMS models
Hierarchical Multi-Tenancy: Organization → User → Branch
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from .context import get_current_organization
import logging

logger = logging.getLogger(__name__)


class TimeStampedModel(models.Model):
    """Abstract base model with timestamps"""
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


# ============================================================================
# ORGANIZATION MODEL - Core Multi-Tenancy
# ============================================================================

class Organization(models.Model):
    """Core tenant entity representing a customer organization."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUID - the ONLY key used for data isolation",
    )
    name = models.CharField(max_length=255, db_index=True)
    logo = models.ImageField(upload_to='organizations/logos/', null=True, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    timezone = models.CharField(max_length=100, default='Asia/Kolkata')
    currency = models.CharField(max_length=3, default='INR')
    subscription_status = models.CharField(
        max_length=20,
        choices=[
            ('trial', 'Trial'),
            ('active', 'Active'),
            ('past_due', 'Past Due'),
            ('cancelled', 'Cancelled'),
            ('suspended', 'Suspended'),
        ],
        default='trial',
        db_index=True,
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']
        indexes = [
            models.Index(fields=['subscription_status', 'is_active']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.name or not self.name.strip():
            raise ValidationError("Organization name is required")


# ============================================================================
# ORGANIZATION-BASED MANAGER - Auto-filters by organization context
# ============================================================================

class OrganizationManager(models.Manager):
    """
    Manager that automatically filters queries by current organization context.
    
    PRODUCTION SAFETY: Raises RuntimeError if organization context is missing
    in production to prevent accidental data leakage across organizations.
    """
    
    def get_queryset(self):
        """Filter all queries by current organization context"""
        qs = super().get_queryset()
        org = get_current_organization()
        
        if org is None:
            # PRODUCTION SAFETY CHECK
            if getattr(settings, 'ENVIRONMENT', 'development') == 'production' and \
               getattr(settings, 'REQUIRE_ORGANIZATION_CONTEXT', True):
                raise RuntimeError(
                    "Organization context is required in production. "
                    "All queries must have organization set via middleware or explicitly."
                )
            
            # 🛡️ MIGRATION SAFETY: Don't log spam during management commands
            import sys
            is_management_cmd = any(cmd in sys.argv for cmd in ['makemigrations', 'migrate', 'collectstatic', 'check'])
            
            # In development, return unfiltered queryset for debugging
            if not is_management_cmd:
                logger.warning("No organization context set - returning unfiltered queryset")
            return qs
        
        return qs.filter(organization_id=org.id)
    
    def all_organizations(self):
        """Get objects from all organizations (admin/reporting use only)"""
        return super().get_queryset()


# ============================================================================
# ORGANIZATION ENTITY - Base class for all organization-scoped models
# ============================================================================

class SoftDeleteManager(models.Manager):
    """Manager that filters out soft-deleted objects"""
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    
    def all_with_deleted(self):
        return super().get_queryset()
    
    def deleted_only(self):
        return super().get_queryset().filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """Abstract model with soft delete capability"""
    
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_deleted'
    )
    
    objects = SoftDeleteManager()
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def delete(self, using=None, keep_parents=False, hard_delete=False):
        if hard_delete:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])
    
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])


class AuditModel(models.Model):
    """Abstract model with audit fields"""
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated'
    )
    
    class Meta:
        abstract = True


class EnterpriseModel(TimeStampedModel, SoftDeleteModel, AuditModel):
    """
    Global (non-tenant-scoped) base model.

    Use for platform-wide entities managed exclusively by superadmins,
    e.g. Plans, global config, platform announcements.
    Provides UUID PK, timestamps, soft-delete, and audit fields but
    deliberately omits the ``organization`` FK so the record is not
    scoped to any single tenant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


class OrganizationEntity(TimeStampedModel, SoftDeleteModel, AuditModel):
    """
    Tenant-scoped enterprise base with automatic organization isolation.

    Provides UUID PK, timestamps, soft-delete, audit fields, and the
    ``organization`` FK for tenant scoping.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        db_index=True,
        related_name='%(app_label)s_%(class)s_set',
        help_text="Organization this record belongs to (primary isolation key)",
    )

    class Meta:
        abstract = True


class MetadataModel(models.Model):
    """Abstract mixin that adds a generic JSON metadata field."""

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class OrganizationDomain(OrganizationEntity):
    """Maps custom domains to organizations for white-label access."""

    domain_name = models.CharField(max_length=255, unique=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ['domain_name']
        verbose_name = 'Organization Domain'
        verbose_name_plural = 'Organization Domains'
        indexes = [
            models.Index(fields=['organization', 'is_primary']),
            models.Index(fields=['domain_name']),
        ]

    def __str__(self):
        return f"{self.domain_name} → {self.organization.name}"

    def save(self, *args, **kwargs):
        self.domain_name = (self.domain_name or '').strip().lower()
        super().save(*args, **kwargs)


class AuditLog(OrganizationEntity):
    """System-wide audit log for tracking all changes"""
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # User info
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    user_email = models.EmailField(null=True, blank=True)
    
    # Action info
    action = models.CharField(max_length=50, db_index=True)
    resource_type = models.CharField(max_length=100, db_index=True)
    resource_id = models.CharField(max_length=100, db_index=True)
    resource_repr = models.CharField(max_length=255, null=True, blank=True)
    
    # Change data
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    
    # Request context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    request_id = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['organization', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
    
    def __str__(self):
        return f"{self.action} {self.resource_type} by {self.user_email}"


class Announcement(OrganizationEntity):
    """Organization-wide announcements"""
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    title = models.CharField(max_length=255)
    content = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    
    target_all = models.BooleanField(default=True)
    target_departments = models.JSONField(default=list, blank=True)
    target_branches = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ['-is_pinned', '-published_at']
        indexes = [
            models.Index(fields=['organization', 'is_published', '-published_at']),
        ]
    
    def __str__(self):
        return self.title
    
    def is_visible(self):
        if not self.is_published:
            return False
        now = timezone.now()
        if self.expires_at and now > self.expires_at:
            return False
        return True


class OrganizationSettings(OrganizationEntity):
    """Organization-level settings and preferences"""
    
    DATE_FORMAT_CHOICES = [
        ('YYYY-MM-DD', 'YYYY-MM-DD'),
        ('DD/MM/YYYY', 'DD/MM/YYYY'),
        ('MM/DD/YYYY', 'MM/DD/YYYY'),
        ('DD-MM-YYYY', 'DD-MM-YYYY'),
    ]
    
    TIME_FORMAT_CHOICES = [
        ('12h', '12-hour'),
        ('24h', '24-hour'),
    ]
    
    date_format = models.CharField(max_length=20, choices=DATE_FORMAT_CHOICES, default='YYYY-MM-DD')
    time_format = models.CharField(max_length=5, choices=TIME_FORMAT_CHOICES, default='24h')
    week_start_day = models.PositiveSmallIntegerField(default=0)
    
    enable_geofencing = models.BooleanField(default=False)
    enable_face_recognition = models.BooleanField(default=False)
    enable_biometric = models.BooleanField(default=False)
    
    leave_approval_levels = models.PositiveSmallIntegerField(default=1)
    expense_approval_levels = models.PositiveSmallIntegerField(default=1)
    
    probation_period_days = models.PositiveIntegerField(default=90)
    notice_period_days = models.PositiveIntegerField(default=30)
    
    payroll_cycle_day = models.PositiveSmallIntegerField(default=1)
    enable_auto_payroll = models.BooleanField(default=False)
    
    branding_primary_color = models.CharField(max_length=7, default='#1976d2')
    branding_secondary_color = models.CharField(max_length=7, default='#dc004e')
    
    custom_settings = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name_plural = 'Organization Settings'
    
    def __str__(self):
        return f"Settings for {self.organization}"
    
    @classmethod
    def get_for_organization(cls, organization):
        settings, _ = cls.objects.get_or_create(organization=organization)
        return settings


class FeatureFlag(OrganizationEntity):
    """Feature flags for controlling feature availability per organization."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=False)

    enabled_for_all = models.BooleanField(default=False)
    enabled_users = models.JSONField(default=list, blank=True)
    enabled_percentage = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['name']
        unique_together = [('organization', 'name')]

    def __str__(self):
        return f"{self.name} ({self.organization})"

    def is_enabled_for(self, organization_id=None, user_id=None):
        if not self.is_enabled:
            return False

        if organization_id and self.organization_id != organization_id:
            return False

        if self.enabled_for_all:
            return True

        if user_id and str(user_id) in self.enabled_users:
            return True

        if user_id and 0 < self.enabled_percentage <= 100:
            import hashlib

            digest = hashlib.sha256(f"{self.id}:{user_id}".encode()).hexdigest()
            bucket = int(digest, 16) % 100
            return bucket < self.enabled_percentage

        return False
