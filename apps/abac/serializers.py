"""
ABAC Serializers
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import (
    AttributeType,
    Policy,
    PolicyRule,
    UserPolicy,
    GroupPolicy,
    PolicyLog,
    Role,
    UserRole,
    Permission,
    RoleAssignment,
)


class AttributeTypeSerializer(serializers.ModelSerializer):
    """Serializer for attribute types"""
    
    organization = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AttributeType
        fields = [
            'id', 'organization', 'name', 'code', 'category', 'data_type',
            'description', 'allowed_values'
        ]
        read_only_fields = ['id', 'organization']


class PolicyRuleSerializer(serializers.ModelSerializer):
    """Serializer for policy rules"""
    
    attribute_type_name = serializers.CharField(source='attribute_type.name', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = PolicyRule
        fields = [
            'id', 'organization', 'policy', 'attribute_type', 'attribute_type_name', 'attribute_path',
            'operator', 'value', 'negate', 'is_active'
        ]
        read_only_fields = ['id', 'organization']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request') if hasattr(self, 'context') else None
        org = getattr(request, 'organization', None) if request else None
        policy = attrs.get('policy') or getattr(self.instance, 'policy', None)

        if org and policy and str(policy.organization_id) != str(org.id):
            raise serializers.ValidationError('Policy must belong to the active organization.')

        return attrs


class PolicySerializer(serializers.ModelSerializer):
    """Serializer for policies"""
    
    rules = PolicyRuleSerializer(many=True, read_only=True)
    rules_count = serializers.SerializerMethodField()
    assigned_users_count = serializers.SerializerMethodField()
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Policy
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'policy_type', 'effect',
            'priority', 'resource_type', 'resource_id', 'actions',
            'combine_logic', 'is_active', 'valid_from', 'valid_until',
            'rules', 'rules_count', 'assigned_users_count'
        ]
        read_only_fields = ['id', 'organization']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_rules_count(self, obj):
        return obj.rules.filter(is_active=True).count()
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_assigned_users_count(self, obj):
        return obj.user_assignments.filter(is_active=True).count()


class PolicyDetailSerializer(PolicySerializer):
    """Detailed policy serializer with all rules"""
    
    class Meta(PolicySerializer.Meta):
        fields = PolicySerializer.Meta.fields


class UserPolicySerializer(serializers.ModelSerializer):
    """Serializer for user policy assignments"""
    
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    policy_code = serializers.CharField(source='policy.code', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    assigned_by_email = serializers.CharField(source='assigned_by.email', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = UserPolicy
        fields = [
            'id', 'organization', 'user', 'user_email', 'policy', 'policy_name', 'policy_code',
            'priority_override', 'is_active', 'assigned_by', 'assigned_by_email',
            'assigned_at', 'valid_from', 'valid_until'
        ]
        read_only_fields = ['id', 'organization', 'assigned_at']


class GroupPolicySerializer(serializers.ModelSerializer):
    """Serializer for group policy assignments"""
    
    policies_data = PolicySerializer(source='policies', many=True, read_only=True)
    policies_count = serializers.SerializerMethodField()
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = GroupPolicy
        fields = [
            'id', 'organization', 'name', 'group_type', 'group_value', 'policies',
            'policies_data', 'policies_count', 'is_active'
        ]
        read_only_fields = ['id', 'organization']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_policies_count(self, obj):
        return obj.policies.filter(is_active=True).count()


class PolicyLogSerializer(serializers.ModelSerializer):
    """Serializer for policy evaluation logs"""
    
    user_email = serializers.CharField(source='user.email', read_only=True)
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = PolicyLog
        fields = [
            'id', 'organization', 'user', 'user_email', 'policy', 'policy_name',
            'resource_type', 'resource_id', 'action', 'result',
            'evaluated_at', 'subject_attributes', 'resource_attributes',
            'environment_attributes', 'policies_evaluated', 'decision_reason'
        ]
        read_only_fields = [
            'id', 'organization', 'user', 'user_email', 'policy', 'policy_name',
            'resource_type', 'resource_id', 'action', 'result',
            'evaluated_at', 'subject_attributes', 'resource_attributes',
            'environment_attributes', 'policies_evaluated', 'decision_reason'
        ]


# Legacy compatibility serializers
class RoleSerializer(serializers.ModelSerializer):
    """Legacy Role serializer for backward compatibility"""
    
    policies_data = PolicySerializer(source='policies', many=True, read_only=True)
    user_count = serializers.SerializerMethodField()
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Role
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'is_active',
            'policies', 'policies_data', 'user_count'
        ]
        read_only_fields = ['id', 'organization']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_user_count(self, obj):
        return obj.user_assignments.filter(is_active=True).count()


class UserRoleSerializer(serializers.ModelSerializer):
    """Legacy UserRole serializer"""
    
    role_name = serializers.CharField(source='role.name', read_only=True)
    role_code = serializers.CharField(source='role.code', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = UserRole
        fields = [
            'id', 'user', 'user_email', 'role', 'role_name', 'role_code',
            'is_active', 'assigned_at'
        ]
        read_only_fields = ['id', 'assigned_at']


class PermissionSerializer(serializers.ModelSerializer):
    """Permission serializer"""
    
    organization = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Permission
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'module', 'action', 'permission_type'
        ]
        read_only_fields = ['id', 'organization']


class RoleAssignmentSerializer(serializers.ModelSerializer):
    """Role Assignment serializer for assigning roles to users"""
    
    role_name = serializers.CharField(source='role.name', read_only=True)
    role_code = serializers.CharField(source='role.code', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    assigned_by_email = serializers.CharField(source='assigned_by.email', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = RoleAssignment
        fields = [
            'id', 'organization', 'user', 'user_email', 'role', 'role_name', 'role_code',
            'scope', 'scope_id', 'is_active', 'valid_from', 'valid_until',
            'assigned_by', 'assigned_by_email', 'assigned_at'
        ]
        read_only_fields = ['id', 'organization', 'assigned_at']

