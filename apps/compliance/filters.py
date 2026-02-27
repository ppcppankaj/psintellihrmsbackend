"""Compliance app filters."""
import django_filters
from .models import (
    DataRetentionPolicy, ConsentRecord, LegalHold,
    DataSubjectRequest, AuditExportRequest, RetentionExecution,
)


class DataRetentionPolicyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    action = django_filters.ChoiceFilter(choices=[
        ('archive', 'Archive'), ('delete', 'Delete'), ('anonymize', 'Anonymize'),
    ])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = DataRetentionPolicy
        fields = ['action', 'is_active']


class ConsentRecordFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    granted = django_filters.BooleanFilter()

    class Meta:
        model = ConsentRecord
        fields = ['employee', 'granted']


class LegalHoldFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    start_date_from = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    end_date_to = django_filters.DateFilter(field_name='end_date', lookup_expr='lte')

    class Meta:
        model = LegalHold
        fields = ['is_active']


class DataSubjectRequestFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    request_type = django_filters.ChoiceFilter(choices=[
        ('access', 'Access'), ('delete', 'Delete'),
        ('rectify', 'Rectify'), ('restrict', 'Restrict'),
    ])
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('in_progress', 'In Progress'),
        ('fulfilled', 'Fulfilled'), ('rejected', 'Rejected'),
    ])

    class Meta:
        model = DataSubjectRequest
        fields = ['employee', 'request_type', 'status']


class AuditExportRequestFilter(django_filters.FilterSet):
    requested_by = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('running', 'Running'),
        ('completed', 'Completed'), ('failed', 'Failed'),
    ])

    class Meta:
        model = AuditExportRequest
        fields = ['requested_by', 'status']


class RetentionExecutionFilter(django_filters.FilterSet):
    policy = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('running', 'Running'),
        ('completed', 'Completed'), ('failed', 'Failed'),
    ])
    dry_run = django_filters.BooleanFilter()

    class Meta:
        model = RetentionExecution
        fields = ['policy', 'status', 'dry_run']
