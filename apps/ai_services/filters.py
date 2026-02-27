"""AI Services app filters."""
import django_filters
from .models import AIModelVersion, AIPrediction


class AIModelVersionFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AIModelVersion
        fields = ['is_active']


class AIPredictionFilter(django_filters.FilterSet):
    model_version = django_filters.UUIDFilter()
    human_reviewed = django_filters.BooleanFilter()
    reviewed_by = django_filters.UUIDFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AIPrediction
        fields = ['model_version', 'human_reviewed', 'reviewed_by']
