"""Attendance app filters."""
import django_filters
from .models import (
    Shift, GeoFence, AttendanceRecord, AttendancePunch,
    FraudLog, FaceEmbedding, ShiftAssignment, OvertimeRequest,
)


class ShiftFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    branch = django_filters.UUIDFilter()
    overtime_allowed = django_filters.BooleanFilter()
    is_night_shift = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Shift
        fields = ['branch', 'overtime_allowed', 'is_night_shift', 'is_active']


class GeoFenceFilter(django_filters.FilterSet):
    location = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    is_primary = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = GeoFence
        fields = ['location', 'branch', 'is_primary', 'is_active']


class AttendanceRecordFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('present', 'Present'), ('absent', 'Absent'), ('half_day', 'Half Day'),
        ('late', 'Late'), ('early_out', 'Early Out'), ('on_leave', 'On Leave'),
        ('holiday', 'Holiday'), ('weekend', 'Weekend'), ('wfh', 'WFH'),
    ])
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    is_flagged = django_filters.BooleanFilter()
    is_regularized = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AttendanceRecord
        fields = ['employee', 'branch', 'status', 'date', 'is_flagged', 'is_regularized']


class AttendancePunchFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    punch_type = django_filters.ChoiceFilter(choices=[('in', 'In'), ('out', 'Out')])
    punch_time_after = django_filters.DateTimeFilter(field_name='punch_time', lookup_expr='gte')
    punch_time_before = django_filters.DateTimeFilter(field_name='punch_time', lookup_expr='lte')
    is_flagged = django_filters.BooleanFilter()

    class Meta:
        model = AttendancePunch
        fields = ['employee', 'branch', 'punch_type', 'is_flagged']


class FraudLogFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    fraud_type = django_filters.CharFilter()
    severity = django_filters.ChoiceFilter(choices=[
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical'),
    ])

    class Meta:
        model = FraudLog
        fields = ['employee', 'fraud_type', 'severity']


class ShiftAssignmentFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    shift = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    is_primary = django_filters.BooleanFilter()
    effective_from = django_filters.DateFilter(lookup_expr='gte')
    effective_to = django_filters.DateFilter(lookup_expr='lte')

    class Meta:
        model = ShiftAssignment
        fields = ['employee', 'shift', 'branch', 'is_primary']


class OvertimeRequestFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'),
    ])

    class Meta:
        model = OvertimeRequest
        fields = ['employee', 'branch', 'status']
