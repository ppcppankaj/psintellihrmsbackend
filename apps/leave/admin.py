"""
Leave Admin
"""

from django.contrib import admin
from apps.core.admin_mixins import BranchAwareAdminMixin, OrganizationAwareAdminMixin
from .models import (
    LeaveType,
    LeavePolicy,
    LeaveBalance,
    LeaveRequest,
    LeaveApproval,
    Holiday,
    LeaveEncashment,
    CompensatoryLeave,
    HolidayCalendar,
    HolidayCalendarEntry,
)


@admin.register(LeaveType)
class LeaveTypeAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'annual_quota', 'accrual_type', 'is_paid', 'carry_forward_allowed', 'is_active']
    list_filter = ['accrual_type', 'is_paid', 'carry_forward_allowed', 'encashment_allowed', 'is_active']
    search_fields = ['name', 'code']
    ordering = ['name']


@admin.register(LeavePolicy)
class LeavePolicyAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'sandwich_rule', 'probation_leave_allowed', 'negative_balance_allowed', 'is_active']
    list_filter = ['sandwich_rule', 'probation_leave_allowed', 'is_active']
    search_fields = ['name']


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'year', 'opening_balance', 'accrued', 'taken', 'available_balance']
    list_filter = ['year', 'leave_type']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee', 'leave_type']
    ordering = ['-year']


@admin.register(LeaveRequest)
class LeaveRequestAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'branch', 'start_date', 'end_date', 'total_days', 'status', 'current_approver', 'created_at']
    list_filter = ['status', 'leave_type', 'branch', 'start_date']
    search_fields = ['employee__employee_id', 'employee__user__email', 'reason']
    raw_id_fields = ['employee', 'leave_type', 'branch', 'current_approver']
    date_hierarchy = 'start_date'
    ordering = ['-created_at']


@admin.register(LeaveApproval)
class LeaveApprovalAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['leave_request', 'approver', 'branch', 'level', 'action', 'created_at']
    list_filter = ['action', 'level', 'branch']
    search_fields = ['leave_request__employee__employee_id', 'approver__employee_id']
    raw_id_fields = ['leave_request', 'approver', 'branch']


@admin.register(Holiday)
class HolidayAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'date', 'branch', 'is_optional', 'is_restricted', 'is_active']
    list_filter = ['is_optional', 'is_restricted', 'branch', 'is_active', 'date']
    search_fields = ['name']
    raw_id_fields = ['branch']
    date_hierarchy = 'date'
    filter_horizontal = ['locations']


@admin.register(LeaveEncashment)
class LeaveEncashmentAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'year', 'days_requested', 'days_approved', 'status', 'per_day_amount', 'total_amount']
    list_filter = ['status', 'leave_type', 'year']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee', 'leave_type', 'approved_by', 'paid_in_payroll']
    ordering = ['-created_at']


@admin.register(CompensatoryLeave)
class CompensatoryLeaveAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'work_date', 'work_type', 'days_credited', 'status', 'expiry_date']
    list_filter = ['status', 'work_type', 'expiry_date']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee', 'approved_by', 'used_in_leave_request']
    date_hierarchy = 'work_date'


@admin.register(HolidayCalendar)
class HolidayCalendarAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'year', 'country', 'is_default', 'is_active']
    list_filter = ['year', 'country', 'is_active']
    search_fields = ['name', 'code']
    filter_horizontal = ['locations']


@admin.register(HolidayCalendarEntry)
class HolidayCalendarEntryAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['calendar', 'name', 'date', 'day_of_week', 'is_optional', 'is_restricted']
    list_filter = ['calendar', 'is_optional', 'is_restricted', 'date']
    search_fields = ['name', 'calendar__name']
