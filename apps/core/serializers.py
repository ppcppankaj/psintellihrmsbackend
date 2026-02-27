from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import (
    Announcement,
    AuditLog,
    FeatureFlag,
    Organization,
    OrganizationDomain,
    OrganizationSettings,
)


class OrganizationSerializer(serializers.ModelSerializer):
    """
    🏢 Organization Serializer
    
    Superuser: Full read/write access to all orgs
    Org Admin: Read-only access to own org
    Regular User: No access
    """
    
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'logo', 'email', 'phone', 'website',
            'timezone', 'currency', 'subscription_status', 'trial_ends_at',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_name(self, value):
        """Ensure organization name is unique (case-insensitive)"""
        queryset = Organization.objects.filter(name__iexact=value)
        
        # Exclude current instance if updating
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("Organization name must be unique.")
        
        return value


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'timestamp', 'user', 'user_name', 'user_email',
            'organization', 'organization_name',
            'action', 'resource_type', 'resource_id', 'resource_repr',
            'old_values', 'new_values', 'changed_fields',
            'ip_address', 'user_agent', 'request_id'
        ]
        read_only_fields = ['id', 'timestamp']


class FeatureFlagSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = FeatureFlag
        fields = [
            'id', 'organization', 'organization_name',
            'name', 'description', 'is_enabled',
            'enabled_for_all', 'enabled_users',
            'enabled_percentage', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'organization_name', 'created_at', 'updated_at']


class OrganizationDomainSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = OrganizationDomain
        fields = [
            'id', 'organization', 'organization_name',
            'domain_name', 'is_primary', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'organization_name', 'created_at', 'updated_at']


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = [
            'id', 'organization', 'title', 'content', 'priority',
            'published_at', 'expires_at', 'is_published', 'is_pinned',
            'target_all', 'target_departments', 'target_branches',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationSettings
        fields = [
            'id', 'organization', 'date_format', 'time_format', 'week_start_day',
            'enable_geofencing', 'enable_face_recognition', 'enable_biometric',
            'leave_approval_levels', 'expense_approval_levels',
            'probation_period_days', 'notice_period_days',
            'payroll_cycle_day', 'enable_auto_payroll',
            'branding_primary_color', 'branding_secondary_color',
            'custom_settings', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
