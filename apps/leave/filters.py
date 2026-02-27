"""Leave app filters."""
import django_filters
from .models import (
    LeaveType, LeavePolicy, LeaveBalance, LeaveRequest,
    LeaveApproval, Holiday, LeaveEncashment, CompensatoryLeave,
    HolidayCalendar, HolidayCalendarEntry,
)


class LeaveTypeFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    accrual_type = django_filters.CharFilter()
    is_paid = django_filters.BooleanFilter()
    carry_forward_allowed = django_filters.BooleanFilter()
    requires_approval = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = LeaveType
        fields = ['accrual_type', 'is_paid', 'carry_forward_allowed', 'requires_approval', 'is_active']


class LeavePolicyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = LeavePolicy
        fields = ['is_active']


class LeaveBalanceFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    leave_type = django_filters.UUIDFilter()

    class Meta:
        model = LeaveBalance
        fields = ['employee', 'leave_type']


class LeaveRequestFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    leave_type = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'), ('revoked', 'Revoked'),
    ])
    start_date = django_filters.DateFilter()
    end_date = django_filters.DateFilter()
    start_after = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    start_before = django_filters.DateFilter(field_name='start_date', lookup_expr='lte')
    current_approver = django_filters.UUIDFilter()

    class Meta:
        model = LeaveRequest
        fields = ['employee', 'leave_type', 'branch', 'status', 'start_date', 'end_date']


class LeaveApprovalFilter(django_filters.FilterSet):
    leave_request = django_filters.UUIDFilter()
    approver = django_filters.UUIDFilter()
    action = django_filters.CharFilter()

    class Meta:
        model = LeaveApproval
        fields = ['leave_request', 'approver', 'action']


class HolidayFilter(django_filters.FilterSet):
    branch = django_filters.UUIDFilter()
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    is_optional = django_filters.BooleanFilter()
    is_restricted = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Holiday
        fields = ['branch', 'date', 'is_optional', 'is_restricted', 'is_active']


class LeaveEncashmentFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    leave_type = django_filters.UUIDFilter()
    status = django_filters.CharFilter()

    class Meta:
        model = LeaveEncashment
        fields = ['employee', 'leave_type', 'status']


class CompensatoryLeaveFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.CharFilter()
    work_type = django_filters.CharFilter()
    work_date_from = django_filters.DateFilter(field_name='work_date', lookup_expr='gte')
    work_date_to = django_filters.DateFilter(field_name='work_date', lookup_expr='lte')

    class Meta:
        model = CompensatoryLeave
        fields = ['employee', 'status', 'work_type']


class HolidayCalendarFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_default = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = HolidayCalendar
        fields = ['is_default', 'is_active']


class HolidayCalendarEntryFilter(django_filters.FilterSet):
    calendar = django_filters.UUIDFilter()
    date = django_filters.DateFilter()
    is_optional = django_filters.BooleanFilter()

    class Meta:
        model = HolidayCalendarEntry
        fields = ['calendar', 'date', 'is_optional']
