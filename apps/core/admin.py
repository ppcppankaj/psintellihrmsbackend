"""
Core Admin - Secure base classes with automatic org/branch filtering
"""

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from .models import (
    Announcement,
    AuditLog,
    FeatureFlag,
    Organization,
    OrganizationDomain,
    OrganizationSettings,
)
from apps.authentication.models_hierarchy import Branch, BranchUser, OrganizationUser


# ==================== SECURE ADMIN BASE CLASSES ====================
# These MUST be defined before any @admin.register decorators that use them.


class OrgBranchAdmin(admin.ModelAdmin):
    """
    Secure Base Admin with automatic organization/branch filtering.
    Prevents cross-organization data access in Django admin.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            org_user = OrganizationUser.objects.filter(
                user=request.user, is_active=True
            ).select_related('organization').first()
            if not org_user:
                return qs.none()
            if hasattr(self.model, 'branch'):
                branch_ids = list(
                    BranchUser.objects.filter(user=request.user, is_active=True)
                    .values_list('branch_id', flat=True)
                )
                return qs.filter(branch_id__in=branch_ids) if branch_ids else qs.none()
            elif hasattr(self.model, 'organization'):
                return qs.filter(organization=org_user.organization)
            return qs
        except Exception:
            return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
        try:
            org_user = OrganizationUser.objects.filter(
                user=request.user, is_active=True
            ).select_related('organization').first()
            if not org_user:
                kwargs["queryset"] = db_field.related_model.objects.none()
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            organization = org_user.organization
            if db_field.name == "branch":
                branch_ids = list(
                    BranchUser.objects.filter(user=request.user, is_active=True)
                    .values_list('branch_id', flat=True)
                )
                kwargs["queryset"] = Branch.objects.filter(id__in=branch_ids)
            elif db_field.name in ["department", "designation", "location"]:
                if hasattr(db_field.related_model, 'organization'):
                    kwargs["queryset"] = db_field.related_model.objects.filter(
                        organization=organization
                    )
            elif db_field.name in ["reporting_manager", "approved_by", "created_by"]:
                if db_field.related_model.__name__ == "Employee":
                    branch_ids = list(
                        BranchUser.objects.filter(user=request.user, is_active=True)
                        .values_list('branch_id', flat=True)
                    )
                    kwargs["queryset"] = db_field.related_model.objects.filter(
                        branch_id__in=branch_ids
                    )
        except Exception:
            kwargs["queryset"] = db_field.related_model.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and hasattr(obj, 'created_by') and not obj.created_by:
            obj.created_by = request.user
        if hasattr(obj, 'updated_by'):
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def _check_object_permission(self, request, obj):
        if request.user.is_superuser:
            return True
        try:
            org_user = OrganizationUser.objects.filter(
                user=request.user, is_active=True
            ).select_related('organization').first()
            if not org_user:
                return False
            if hasattr(obj, 'branch'):
                return BranchUser.objects.filter(
                    user=request.user, branch=obj.branch, is_active=True
                ).exists()
            elif hasattr(obj, 'organization'):
                return obj.organization_id == org_user.organization_id
            return True
        except Exception:
            return False


class OrganizationScopedAdmin(admin.ModelAdmin):
    """
    Admin for organization-level resources (no branch filtering).
    Examples: Departments, Designations, Leave Types.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            org_user = OrganizationUser.objects.filter(
                user=request.user, is_active=True
            ).select_related('organization').first()
            if not org_user:
                return qs.none()
            if hasattr(self.model, 'organization'):
                return qs.filter(organization=org_user.organization)
            return qs
        except Exception:
            return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            try:
                org_user = OrganizationUser.objects.filter(
                    user=request.user, is_active=True
                ).select_related('organization').first()
                if org_user and hasattr(db_field.related_model, 'organization'):
                    kwargs["queryset"] = db_field.related_model.objects.filter(
                        organization=org_user.organization
                    )
            except Exception:
                kwargs["queryset"] = db_field.related_model.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ReadOnlyOrgBranchAdmin(OrgBranchAdmin):
    """Read-only admin with organization filtering (audit logs, reports)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==================== CONCRETE ADMIN REGISTRATIONS ====================


class OrganizationDomainInline(admin.TabularInline):
    model = OrganizationDomain
    extra = 1
    fields = ['domain_name', 'is_primary', 'is_active']
    min_num = 0
    verbose_name_plural = "Custom Domains"


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'subscription_status', 'is_active', 'created_at']
    list_filter = ['subscription_status', 'is_active', 'created_at']
    search_fields = ['name', 'email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {'fields': ('id', 'name', 'email')}),
        ('Business Settings', {'fields': ('timezone', 'currency')}),
        ('Subscription', {'fields': ('subscription_status', 'is_active')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    inlines = [OrganizationDomainInline]
    ordering = ['-created_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if getattr(request.user, 'is_org_admin', False) and getattr(request.user, 'organization', None):
            return qs.filter(id=request.user.organization_id)
        return qs.none()

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyOrgBranchAdmin):
    list_display = ['timestamp', 'organization', 'user_email', 'action', 'resource_type', 'resource_id', 'ip_address']
    list_filter = ['action', 'resource_type', 'timestamp', 'organization']
    search_fields = ['user_email', 'resource_id', 'ip_address', 'organization__name']
    readonly_fields = [
        'id', 'timestamp', 'organization', 'user', 'user_email', 'action',
        'resource_type', 'resource_id', 'resource_repr',
        'old_values', 'new_values', 'changed_fields',
        'ip_address', 'user_agent', 'request_id',
    ]
    ordering = ['-timestamp']


@admin.register(FeatureFlag)
class FeatureFlagAdmin(OrganizationScopedAdmin):
    list_display = ['name', 'organization', 'is_enabled', 'enabled_for_all', 'enabled_percentage', 'updated_at']
    list_filter = ['organization', 'is_enabled', 'enabled_for_all']
    search_fields = ['name', 'description', 'organization__name']
    ordering = ['name']


@admin.register(OrganizationDomain)
class OrganizationDomainAdmin(OrganizationScopedAdmin):
    list_display = ['domain_name', 'organization', 'is_primary', 'is_active', 'updated_at']
    list_filter = ['is_active', 'is_primary', 'organization']
    search_fields = ['domain_name', 'organization__name']
    autocomplete_fields = ['organization']


@admin.register(Announcement)
class AnnouncementAdmin(OrganizationScopedAdmin):
    list_display = ['title', 'organization', 'priority', 'is_published', 'is_pinned', 'published_at']
    list_filter = ['organization', 'priority', 'is_published', 'is_pinned']
    search_fields = ['title', 'organization__name']
    ordering = ['-published_at']


@admin.register(OrganizationSettings)
class OrganizationSettingsAdmin(OrganizationScopedAdmin):
    list_display = ['organization', 'date_format', 'time_format', 'week_start_day', 'is_active']
    list_filter = ['organization', 'is_active']
    search_fields = ['organization__name']

