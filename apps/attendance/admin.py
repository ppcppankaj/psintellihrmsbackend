"""
Attendance Admin
"""

from django.contrib import admin
from apps.core.admin_mixins import BranchAwareAdminMixin, OrganizationAwareAdminMixin
from .models import (
    Shift, GeoFence, AttendanceRecord,
    AttendancePunch, FraudLog, FaceEmbedding,
    ShiftAssignment, OvertimeRequest
)


@admin.register(Shift)
class ShiftAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'branch', 'start_time', 'end_time', 'working_hours', 'is_night_shift', 'is_active']
    list_filter = ['is_night_shift', 'overtime_allowed', 'branch', 'is_active']
    search_fields = ['name', 'code']
    raw_id_fields = ['branch']
    ordering = ['name']


@admin.register(GeoFence)
class GeoFenceAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'location', 'branch', 'radius_meters', 'is_primary']
    list_filter = ['branch', 'is_primary']
    search_fields = ['name', 'location__name']
    raw_id_fields = ['location', 'branch']


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'date', 'status', 'total_hours', 'is_flagged', 'is_regularized']
    list_filter = ['status', 'is_flagged', 'is_regularized', 'branch', 'date']
    search_fields = ['employee__employee_id', 'employee__first_name', 'employee__last_name']
    raw_id_fields = ['employee', 'branch', 'approved_by']
    date_hierarchy = 'date'


@admin.register(AttendancePunch)
class AttendancePunchAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'punch_type', 'punch_time', 'fraud_score', 'face_verified']
    list_filter = ['punch_type', 'face_verified', 'branch', 'punch_time']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee', 'branch', 'attendance', 'geo_fence']


@admin.register(FraudLog)
class FraudLogAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'fraud_type', 'severity', 'action_taken', 'reviewed_by', 'created_at']
    list_filter = ['fraud_type', 'severity', 'action_taken']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee', 'punch', 'reviewed_by']
    ordering = ['-created_at']


@admin.register(FaceEmbedding)
class FaceEmbeddingAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'embedding_model', 'is_primary', 'quality_score', 'created_at']
    list_filter = ['embedding_model', 'is_primary']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee']


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'shift', 'branch', 'effective_from', 'effective_to', 'is_primary', 'is_active']
    list_filter = ['is_primary', 'is_active', 'branch', 'shift']
    search_fields = ['employee__employee_id', 'shift__name']
    raw_id_fields = ['employee', 'shift', 'branch']


@admin.register(OvertimeRequest)
class OvertimeRequestAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'attendance', 'requested_hours', 'approved_hours', 'status', 'reviewed_by']
    list_filter = ['status', 'branch']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee', 'attendance', 'branch', 'reviewed_by']
