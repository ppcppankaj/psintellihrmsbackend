"""
Compliance Serializers
"""

from rest_framework import serializers
from .models import (
    DataRetentionPolicy,
    ConsentRecord,
    LegalHold,
    DataSubjectRequest,
    AuditExportRequest,
    RetentionExecution,
)


class DataRetentionPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = DataRetentionPolicy
        fields = [
            'id', 'organization', 'name', 'entity_type', 'retention_days',
            'action', 'date_field', 'filter_criteria',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class ConsentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        fields = [
            'id', 'organization', 'employee', 'consent_type', 'granted',
            'granted_at', 'revoked_at', 'ip_address',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class LegalHoldSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalHold
        fields = [
            'id', 'organization', 'name', 'description', 'employees',
            'start_date', 'end_date',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class DataSubjectRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSubjectRequest
        fields = [
            'id', 'organization', 'request_type', 'status',
            'requested_by', 'employee', 'details', 'due_date',
            'processed_by', 'processed_at', 'response_file', 'notes',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class AuditExportRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditExportRequest
        fields = [
            'id', 'organization', 'requested_by', 'filters', 'status',
            'file', 'row_count', 'started_at', 'completed_at', 'error_message',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class RetentionExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetentionExecution
        fields = [
            'id', 'organization', 'policy', 'requested_by', 'status',
            'dry_run', 'started_at', 'completed_at', 'affected_count',
            'details', 'error_message',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
