"""Notification Serializers"""

from rest_framework import serializers

from .models import Notification, NotificationPreference, NotificationTemplate


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'organization', 'name', 'code', 'subject', 'body',
            'channel', 'variables', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class NotificationSerializer(serializers.ModelSerializer):
    template_details = NotificationTemplateSerializer(source='template', read_only=True)
    recipient_id = serializers.UUIDField(source='recipient.id', read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'organization', 'recipient', 'recipient_id', 'employee_name',
            'template', 'template_details', 'channel', 'subject', 'body',
            'status', 'priority', 'metadata', 'sent_at', 'read_at', 'scheduled_for',
            'delivery_attempts', 'entity_type', 'entity_id',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'organization', 'recipient', 'recipient_id', 'employee_name',
            'template_details', 'status', 'sent_at', 'read_at', 'scheduled_for',
            'delivery_attempts', 'created_at', 'updated_at'
        ]

    def get_employee_name(self, obj):  # noqa: D401 - simple helper
        employee = getattr(obj, 'recipient', None)
        if not employee:
            return None
        if hasattr(employee, 'full_name'):
            return employee.full_name
        user = getattr(employee, 'user', None)
        return user.get_full_name() if user else None


class NotificationDispatchSerializer(serializers.Serializer):
    """Validate manual/bulk dispatch requests."""

    recipient_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    template_code = serializers.CharField(required=False)
    context = serializers.DictField(required=False, default=dict)
    subject = serializers.CharField(required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)
    channel = serializers.ChoiceField(
        choices=['in_app', 'email', 'push', 'sms', 'whatsapp', 'slack', 'teams'],
        default='in_app',
    )
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high', 'critical'],
        default='normal',
    )
    metadata = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        template_code = attrs.get('template_code')
        subject = attrs.get('subject')
        body = attrs.get('body')
        if not template_code and (not subject or not body):
            raise serializers.ValidationError('Provide template_code or both subject and body')
        return attrs


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'organization', 'user',
            'email_enabled', 'push_enabled', 'sms_enabled',
            'leave_notifications', 'attendance_notifications',
            'payroll_notifications', 'task_notifications', 'announcement_notifications',
            'quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at', 'user']


class PushNotificationSerializer(serializers.Serializer):
    recipient_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    title = serializers.CharField(max_length=255)
    body = serializers.CharField()
    data = serializers.DictField(required=False, default=dict)
    priority = serializers.ChoiceField(choices=['low', 'normal', 'high'], default='normal')


class SendDigestSerializer(serializers.Serializer):
    digest_type = serializers.ChoiceField(choices=['daily', 'weekly'], default='daily')
    recipient_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class NotificationReadSerializer(serializers.Serializer):
    read_at = serializers.DateTimeField(required=False)
