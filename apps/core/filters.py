"""Core app filters."""
import django_filters
from .models import (
    Announcement, AuditLog, FeatureFlag,
    Organization, OrganizationDomain, OrganizationSettings,
)


class OrganizationFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    subscription_status = django_filters.ChoiceFilter(choices=[
        ('trial', 'Trial'), ('active', 'Active'), ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'), ('suspended', 'Suspended'),
    ])
    is_active = django_filters.BooleanFilter()
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Organization
        fields = ['name', 'subscription_status', 'is_active']


class OrganizationDomainFilter(django_filters.FilterSet):
    domain_name = django_filters.CharFilter(lookup_expr='icontains')
    is_primary = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = OrganizationDomain
        fields = ['domain_name', 'is_primary', 'is_active']


class AuditLogFilter(django_filters.FilterSet):
    action = django_filters.CharFilter()
    resource_type = django_filters.CharFilter()
    resource_id = django_filters.CharFilter()
    user = django_filters.UUIDFilter()
    user_email = django_filters.CharFilter(lookup_expr='icontains')
    timestamp_after = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    timestamp_before = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')

    class Meta:
        model = AuditLog
        fields = ['action', 'resource_type', 'resource_id', 'user', 'user_email']


class AnnouncementFilter(django_filters.FilterSet):
    priority = django_filters.ChoiceFilter(choices=[
        ('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('urgent', 'Urgent'),
    ])
    is_published = django_filters.BooleanFilter()
    is_pinned = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    published_after = django_filters.DateTimeFilter(field_name='published_at', lookup_expr='gte')
    published_before = django_filters.DateTimeFilter(field_name='published_at', lookup_expr='lte')

    class Meta:
        model = Announcement
        fields = ['priority', 'is_published', 'is_pinned', 'is_active']


class FeatureFlagFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_enabled = django_filters.BooleanFilter()
    enabled_for_all = django_filters.BooleanFilter()

    class Meta:
        model = FeatureFlag
        fields = ['name', 'is_enabled', 'enabled_for_all']


class OrganizationSettingsFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    enable_geofencing = django_filters.BooleanFilter()
    enable_face_recognition = django_filters.BooleanFilter()

    class Meta:
        model = OrganizationSettings
        fields = ['is_active', 'enable_geofencing', 'enable_face_recognition']
