"""Workflows app filters."""
import django_filters
from .models import (
    WorkflowDefinition, WorkflowStep, WorkflowInstance, WorkflowAction,
)


class WorkflowDefinitionFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    auto_approve_on_sla = django_filters.BooleanFilter()

    class Meta:
        model = WorkflowDefinition
        fields = ['is_active', 'auto_approve_on_sla']


class WorkflowStepFilter(django_filters.FilterSet):
    workflow = django_filters.UUIDFilter()
    approver_type = django_filters.CharFilter()
    is_optional = django_filters.BooleanFilter()

    class Meta:
        model = WorkflowStep
        fields = ['workflow', 'approver_type', 'is_optional']


class WorkflowInstanceFilter(django_filters.FilterSet):
    workflow = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('in_progress', 'In Progress'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('cancelled', 'Cancelled'),
        ('escalated', 'Escalated'),
    ])
    current_approver = django_filters.UUIDFilter()
    started_after = django_filters.DateTimeFilter(field_name='started_at', lookup_expr='gte')
    started_before = django_filters.DateTimeFilter(field_name='started_at', lookup_expr='lte')

    class Meta:
        model = WorkflowInstance
        fields = ['workflow', 'status', 'current_approver']


class WorkflowActionFilter(django_filters.FilterSet):
    instance = django_filters.UUIDFilter()
    actor = django_filters.UUIDFilter()
    action = django_filters.CharFilter()

    class Meta:
        model = WorkflowAction
        fields = ['instance', 'actor', 'action']
