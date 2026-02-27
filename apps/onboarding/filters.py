"""Onboarding app filters."""
import django_filters
from .models import (
    OnboardingTemplate, OnboardingTaskTemplate,
    EmployeeOnboarding, OnboardingTaskProgress, OnboardingDocument,
)


class OnboardingTemplateFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    department = django_filters.UUIDFilter()
    designation = django_filters.UUIDFilter()
    location = django_filters.UUIDFilter()
    is_default = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = OnboardingTemplate
        fields = ['department', 'designation', 'location', 'is_default', 'is_active']


class OnboardingTaskTemplateFilter(django_filters.FilterSet):
    template = django_filters.UUIDFilter()
    stage = django_filters.CharFilter()
    assigned_to_type = django_filters.CharFilter()
    is_mandatory = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = OnboardingTaskTemplate
        fields = ['template', 'stage', 'assigned_to_type', 'is_mandatory']


class EmployeeOnboardingFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    template = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('not_started', 'Not Started'), ('in_progress', 'In Progress'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])
    hr_responsible = django_filters.UUIDFilter()
    joining_date_from = django_filters.DateFilter(field_name='joining_date', lookup_expr='gte')
    joining_date_to = django_filters.DateFilter(field_name='joining_date', lookup_expr='lte')

    class Meta:
        model = EmployeeOnboarding
        fields = ['employee', 'template', 'status', 'hr_responsible']


class OnboardingTaskProgressFilter(django_filters.FilterSet):
    onboarding = django_filters.UUIDFilter()
    task_template = django_filters.UUIDFilter()
    assigned_to = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('in_progress', 'In Progress'),
        ('completed', 'Completed'), ('skipped', 'Skipped'), ('overdue', 'Overdue'),
    ])
    is_mandatory = django_filters.BooleanFilter()

    class Meta:
        model = OnboardingTaskProgress
        fields = ['onboarding', 'status', 'assigned_to', 'is_mandatory']


class OnboardingDocumentFilter(django_filters.FilterSet):
    onboarding = django_filters.UUIDFilter()
    document_type = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('uploaded', 'Uploaded'),
        ('verified', 'Verified'), ('rejected', 'Rejected'),
    ])
    is_mandatory = django_filters.BooleanFilter()

    class Meta:
        model = OnboardingDocument
        fields = ['onboarding', 'document_type', 'status', 'is_mandatory']
