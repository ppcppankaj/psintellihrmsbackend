"""Performance app filters."""
import django_filters
from .models import (
    PerformanceCycle, OKRObjective, KeyResult,
    PerformanceReview, ReviewFeedback, KeyResultArea,
    EmployeeKRA, KPI, Competency, EmployeeCompetency,
    TrainingRecommendation,
)


class PerformanceCycleFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('active', 'Active'),
        ('review', 'Review'), ('completed', 'Completed'),
    ])
    is_active = django_filters.BooleanFilter()
    start_date_from = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    end_date_to = django_filters.DateFilter(field_name='end_date', lookup_expr='lte')

    class Meta:
        model = PerformanceCycle
        fields = ['status', 'is_active']


class OKRObjectiveFilter(django_filters.FilterSet):
    cycle = django_filters.UUIDFilter()
    employee = django_filters.UUIDFilter()
    parent = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('active', 'Active'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])

    class Meta:
        model = OKRObjective
        fields = ['cycle', 'employee', 'parent', 'status']


class KeyResultFilter(django_filters.FilterSet):
    objective = django_filters.UUIDFilter()
    metric_type = django_filters.CharFilter()

    class Meta:
        model = KeyResult
        fields = ['objective', 'metric_type']


class PerformanceReviewFilter(django_filters.FilterSet):
    cycle = django_filters.UUIDFilter()
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('self_review', 'Self Review'),
        ('manager_review', 'Manager Review'), ('completed', 'Completed'),
    ])

    class Meta:
        model = PerformanceReview
        fields = ['cycle', 'employee', 'status']


class ReviewFeedbackFilter(django_filters.FilterSet):
    review = django_filters.UUIDFilter()
    reviewer = django_filters.UUIDFilter()
    relationship = django_filters.CharFilter()
    is_anonymous = django_filters.BooleanFilter()

    class Meta:
        model = ReviewFeedback
        fields = ['review', 'reviewer', 'relationship', 'is_anonymous']


class KeyResultAreaFilter(django_filters.FilterSet):
    designation = django_filters.UUIDFilter()
    department = django_filters.UUIDFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = KeyResultArea
        fields = ['designation', 'department', 'is_active']


class EmployeeKRAFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    cycle = django_filters.UUIDFilter()
    kra = django_filters.UUIDFilter()

    class Meta:
        model = EmployeeKRA
        fields = ['employee', 'cycle', 'kra']


class KPIFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    employee_kra = django_filters.UUIDFilter()
    metric_type = django_filters.CharFilter()
    is_achieved = django_filters.BooleanFilter()

    class Meta:
        model = KPI
        fields = ['employee', 'employee_kra', 'metric_type', 'is_achieved']


class CompetencyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    category = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Competency
        fields = ['category', 'is_active']


class EmployeeCompetencyFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    competency = django_filters.UUIDFilter()
    cycle = django_filters.UUIDFilter()

    class Meta:
        model = EmployeeCompetency
        fields = ['employee', 'competency', 'cycle']


class TrainingRecommendationFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    competency = django_filters.UUIDFilter()
    cycle = django_filters.UUIDFilter()
    priority = django_filters.CharFilter()
    is_completed = django_filters.BooleanFilter()

    class Meta:
        model = TrainingRecommendation
        fields = ['employee', 'competency', 'cycle', 'priority', 'is_completed']
