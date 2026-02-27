"""Reports app filters."""
import django_filters
from .models import (
    ReportTemplate, ScheduledReport, GeneratedReport, ReportExecution,
)


class ReportTemplateFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = ReportTemplate
        fields = ['is_active']


class ScheduledReportFilter(django_filters.FilterSet):
    template = django_filters.UUIDFilter()
    format = django_filters.ChoiceFilter(choices=[
        ('pdf', 'PDF'), ('excel', 'Excel'), ('csv', 'CSV'),
    ])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = ScheduledReport
        fields = ['template', 'format', 'is_active']


class GeneratedReportFilter(django_filters.FilterSet):
    template = django_filters.UUIDFilter()
    generated_by = django_filters.UUIDFilter()
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')

    class Meta:
        model = GeneratedReport
        fields = ['template', 'generated_by']


class ReportExecutionFilter(django_filters.FilterSet):
    template = django_filters.UUIDFilter()
    requested_by = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('running', 'Running'),
        ('completed', 'Completed'), ('failed', 'Failed'),
    ])
    output_format = django_filters.CharFilter()

    class Meta:
        model = ReportExecution
        fields = ['template', 'requested_by', 'status', 'output_format']
