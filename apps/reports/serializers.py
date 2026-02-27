"""Report Serializers"""
from rest_framework import serializers
from .models import ReportTemplate, ScheduledReport, GeneratedReport, ReportExecution


class ReportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportTemplate
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'report_type',
            'query_config', 'columns', 'filters', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class ScheduledReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledReport
        fields = [
            'id', 'organization', 'template', 'schedule', 'recipients', 'format',
            'last_run', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class GeneratedReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedReport
        fields = [
            'id', 'organization', 'template', 'generated_by', 'filters_applied',
            'file', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class ReportExecutionSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(read_only=True)
    template_code = serializers.CharField(read_only=True)
    requested_by_email = serializers.CharField(source='requested_by.email', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ReportExecution
        fields = [
            'id', 'template', 'template_code', 'template_name',
            'requested_by', 'requested_by_email',
            'filters', 'parameters', 'status', 'status_display',
            'output_format', 'started_at', 'completed_at',
            'execution_time_ms', 'row_count', 'columns',
            'file', 'file_size', 'error_message',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status_display', 'started_at', 'completed_at',
            'execution_time_ms', 'row_count', 'columns',
            'file', 'file_size', 'error_message',
            'created_at', 'updated_at'
        ]


class ReportExecuteRequestSerializer(serializers.Serializer):
    template_id = serializers.UUIDField(required=False)
    template_code = serializers.CharField(required=False)
    output_format = serializers.ChoiceField(choices=ReportExecution.FORMAT_CHOICES, default=ReportExecution.FORMAT_CSV)
    filters = serializers.JSONField(required=False)
    parameters = serializers.JSONField(required=False)
    run_async = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('template_id') and not attrs.get('template_code'):
            raise serializers.ValidationError("template_id or template_code is required")
        return attrs
