"""
ABAC Admin Interface
"""

from django.contrib import admin
from .models import (
    AttributeType, Policy, PolicyRule, UserPolicy, 
    GroupPolicy, PolicyLog, Role, RoleAssignment, UserRole,
    Permission, RolePermission
)
from apps.core.admin_mixins import OrganizationAwareAdminMixin


@admin.register(AttributeType)
class AttributeTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'data_type']
    list_filter = ['category', 'data_type']
    search_fields = ['name', 'code', 'description']
    ordering = ['category', 'name']


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'policy_type', 'effect', 'priority', 'is_active']
    list_filter = ['policy_type', 'effect', 'is_active']
    search_fields = ['name', 'code', 'description', 'resource_type']
    ordering = ['-priority', 'name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'description', 'policy_type', 'effect')
        }),
        ('Resource Targeting', {
            'fields': ('resource_type', 'resource_id', 'actions')
        }),
        ('Rule Configuration', {
            'fields': ('combine_logic', 'priority')
        }),
        ('Validity', {
            'fields': ('is_active', 'valid_from', 'valid_until')
        }),
    )


@admin.register(PolicyRule)
class PolicyRuleAdmin(admin.ModelAdmin):
    list_display = ['policy', 'attribute_type', 'attribute_path', 'operator', 'value', 'negate', 'is_active']
    list_filter = ['operator', 'is_active', 'attribute_type__category']
    search_fields = ['attribute_path', 'policy__name']
    ordering = ['policy', 'id']


@admin.register(UserPolicy)
class UserPolicyAdmin(admin.ModelAdmin):
    list_display = ['user', 'policy', 'is_active', 'assigned_at', 'assigned_by']
    list_filter = ['is_active', 'assigned_at']
    search_fields = ['user__email', 'policy__name']
    ordering = ['-assigned_at']
    raw_id_fields = ['user', 'policy', 'assigned_by']


@admin.register(GroupPolicy)
class GroupPolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'group_type', 'group_value', 'is_active']
    list_filter = ['group_type', 'is_active']
    search_fields = ['name', 'group_value']
    ordering = ['group_type', 'name']
    filter_horizontal = ['policies']


@admin.register(PolicyLog)
class PolicyLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'resource_type', 'action', 'result', 'evaluated_at']
    list_filter = ['result', 'resource_type', 'action', 'evaluated_at']
    search_fields = ['user__email', 'resource_type', 'resource_id']
    ordering = ['-evaluated_at']
    readonly_fields = ['user', 'policy', 'resource_type', 'resource_id', 'action', 
                      'result', 'evaluated_at', 'subject_attributes', 'resource_attributes',
                      'environment_attributes', 'policies_evaluated', 'decision_reason']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(Role)
class RoleAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    search_fields = ['name', 'code']
    filter_horizontal = ['policies']


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['user', 'role', 'scope', 'scope_id', 'is_active']
    list_filter = ['scope', 'is_active']
    raw_id_fields = ['user', 'role', 'assigned_by']


@admin.register(UserRole)
class UserRoleAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['user', 'role', 'is_active', 'assigned_at']
    raw_id_fields = ['user', 'role']


@admin.register(Permission)
class PermissionAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'module', 'action']
    list_filter = ['module', 'permission_type']
    search_fields = ['name', 'code']


@admin.register(RolePermission)
class RolePermissionAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['role', 'permission']
    raw_id_fields = ['role', 'permission']
