"""
Asset Management Admin
"""

from django.contrib import admin
from apps.core.admin_mixins import BranchAwareAdminMixin, OrganizationAwareAdminMixin
from .models import AssetCategory, Asset, AssetAssignment


@admin.register(AssetCategory)
class AssetCategoryAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'created_at']
    search_fields = ['name', 'code']


@admin.register(Asset)
class AssetAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['asset_tag', 'name', 'category', 'branch', 'status', 'current_assignee', 'purchase_date']
    list_filter = ['status', 'category', 'branch']
    search_fields = ['asset_tag', 'name', 'serial_number']
    raw_id_fields = ['current_assignee', 'branch']


@admin.register(AssetAssignment)
class AssetAssignmentAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['asset', 'employee', 'branch', 'assigned_date', 'returned_date', 'is_active']
    list_filter = ['returned_date', 'branch']
    raw_id_fields = ['asset', 'employee', 'branch', 'assigned_by']
