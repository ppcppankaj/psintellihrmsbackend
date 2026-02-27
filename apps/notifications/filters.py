"""Notifications app filters."""
import django_filters
from .models import NotificationTemplate, NotificationPreference, Notification


class NotificationTemplateFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    channel = django_filters.ChoiceFilter(choices=[
        ('email', 'Email'), ('sms', 'SMS'), ('push', 'Push'),
        ('whatsapp', 'WhatsApp'), ('slack', 'Slack'), ('teams', 'Teams'),
    ])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = NotificationTemplate
        fields = ['channel', 'is_active']


class NotificationPreferenceFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter()
    email_enabled = django_filters.BooleanFilter()
    push_enabled = django_filters.BooleanFilter()

    class Meta:
        model = NotificationPreference
        fields = ['user', 'email_enabled', 'push_enabled']


class NotificationFilter(django_filters.FilterSet):
    recipient = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('scheduled', 'Scheduled'), ('sent', 'Sent'),
        ('delivered', 'Delivered'), ('read', 'Read'), ('failed', 'Failed'),
    ])
    priority = django_filters.ChoiceFilter(choices=[
        ('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('critical', 'Critical'),
    ])
    sent_after = django_filters.DateTimeFilter(field_name='sent_at', lookup_expr='gte')
    sent_before = django_filters.DateTimeFilter(field_name='sent_at', lookup_expr='lte')

    class Meta:
        model = Notification
        fields = ['recipient', 'status', 'priority']
