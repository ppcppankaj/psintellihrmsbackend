"""Compliance Admin"""
from django.contrib import admin
from .models import (
    DataRetentionPolicy,
    ConsentRecord,
    LegalHold,
    DataSubjectRequest,
    AuditExportRequest,
    RetentionExecution,
)

@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'entity_type', 'retention_days', 'action', 'is_active']
    list_filter = ['action', 'is_active']

@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ['employee', 'consent_type', 'granted', 'granted_at', 'revoked_at']
    list_filter = ['consent_type', 'granted']
    raw_id_fields = ['employee']

@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'is_active']
    filter_horizontal = ['employees']


@admin.register(DataSubjectRequest)
class DataSubjectRequestAdmin(admin.ModelAdmin):
    list_display = ['request_type', 'status', 'requested_by', 'employee', 'created_at']
    list_filter = ['request_type', 'status']
    search_fields = ['details', 'notes']


@admin.register(AuditExportRequest)
class AuditExportRequestAdmin(admin.ModelAdmin):
    list_display = ['status', 'requested_by', 'row_count', 'created_at']
    list_filter = ['status']


@admin.register(RetentionExecution)
class RetentionExecutionAdmin(admin.ModelAdmin):
    list_display = ['policy', 'status', 'dry_run', 'affected_count', 'created_at']
    list_filter = ['status', 'dry_run']
