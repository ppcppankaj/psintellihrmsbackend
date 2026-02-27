"""Integrations app filters."""
import django_filters
from .models import Integration, Webhook, APIKey


class IntegrationFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_connected = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Integration
        fields = ['is_connected', 'is_active']


class WebhookFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Webhook
        fields = ['is_active']


class APIKeyFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    expired = django_filters.BooleanFilter(method='filter_expired')

    class Meta:
        model = APIKey
        fields = ['is_active']

    def filter_expired(self, queryset, name, value):
        from django.utils import timezone
        now = timezone.now()
        if value:
            return queryset.filter(expires_at__lt=now)
        return queryset.filter(expires_at__gte=now)
