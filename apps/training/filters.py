"""Training app filters."""
import django_filters
from .models import (
    TrainingCategory, TrainingProgram, TrainingMaterial,
    TrainingEnrollment, TrainingCompletion,
)


class TrainingCategoryFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = TrainingCategory
        fields = ['is_active']


class TrainingProgramFilter(django_filters.FilterSet):
    category = django_filters.UUIDFilter()
    delivery_mode = django_filters.ChoiceFilter(choices=[
        ('online', 'Online'), ('onsite', 'Onsite'), ('hybrid', 'Hybrid'),
    ])
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived'),
    ])
    is_mandatory = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    start_date_from = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    end_date_to = django_filters.DateFilter(field_name='end_date', lookup_expr='lte')

    class Meta:
        model = TrainingProgram
        fields = ['category', 'delivery_mode', 'status', 'is_mandatory', 'is_active']


class TrainingMaterialFilter(django_filters.FilterSet):
    program = django_filters.UUIDFilter()
    material_type = django_filters.CharFilter()
    is_required = django_filters.BooleanFilter()

    class Meta:
        model = TrainingMaterial
        fields = ['program', 'material_type', 'is_required']


class TrainingEnrollmentFilter(django_filters.FilterSet):
    program = django_filters.UUIDFilter()
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('enrolled', 'Enrolled'), ('in_progress', 'In Progress'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])
    due_date_from = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')

    class Meta:
        model = TrainingEnrollment
        fields = ['program', 'employee', 'status']


class TrainingCompletionFilter(django_filters.FilterSet):
    enrollment = django_filters.UUIDFilter()
    completed_after = django_filters.DateTimeFilter(field_name='completed_at', lookup_expr='gte')

    class Meta:
        model = TrainingCompletion
        fields = ['enrollment']
