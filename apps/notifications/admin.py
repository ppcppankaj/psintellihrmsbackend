from django.contrib import admin
from apps.core.admin_mixins import OrganizationAwareAdminMixin
from .models import Notification, NotificationPreference, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'channel', 'is_active']
    list_filter = ['channel', 'is_active']
    search_fields = ['name', 'code']


@admin.register(Notification)
class NotificationAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['recipient', 'channel', 'priority', 'status', 'scheduled_for', 'sent_at', 'read_at']
    list_filter = ['status', 'channel', 'priority']
    search_fields = ['recipient__employee_id', 'subject']
    raw_id_fields = ['recipient', 'template']
    readonly_fields = ['metadata', 'delivery_attempts']


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['user', 'email_enabled', 'push_enabled', 'sms_enabled', 'quiet_hours_enabled']
    search_fields = ['user__email', 'user__username']
