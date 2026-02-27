"""ABAC app filters."""
import django_filters
from .models import (
    AttributeType, Policy, PolicyRule, UserPolicy,
    GroupPolicy, PolicyLog, Role, RoleAssignment,
    Permission, RolePermission,
)


class AttributeTypeFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    category = django_filters.ChoiceFilter(choices=[
        ('subject', 'Subject'), ('resource', 'Resource'),
        ('action', 'Action'), ('environment', 'Environment'),
    ])
    data_type = django_filters.ChoiceFilter(choices=[
        ('string', 'String'), ('number', 'Number'), ('boolean', 'Boolean'),
        ('date', 'Date'), ('time', 'Time'), ('list', 'List'),
    ])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AttributeType
        fields = ['category', 'data_type', 'is_active']


class PolicyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    policy_type = django_filters.CharFilter()
    effect = django_filters.ChoiceFilter(choices=[('allow', 'Allow'), ('deny', 'Deny')])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Policy
        fields = ['policy_type', 'effect', 'is_active']


class PolicyRuleFilter(django_filters.FilterSet):
    policy = django_filters.UUIDFilter()
    attribute_type = django_filters.UUIDFilter()
    operator = django_filters.CharFilter()

    class Meta:
        model = PolicyRule
        fields = ['policy', 'attribute_type', 'operator']


class UserPolicyFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter()
    policy = django_filters.UUIDFilter()

    class Meta:
        model = UserPolicy
        fields = ['user', 'policy']


class GroupPolicyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    group_type = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = GroupPolicy
        fields = ['group_type', 'is_active']


class PolicyLogFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter()
    policy = django_filters.UUIDFilter()
    result = django_filters.BooleanFilter()
    evaluated_after = django_filters.DateTimeFilter(field_name='evaluated_at', lookup_expr='gte')

    class Meta:
        model = PolicyLog
        fields = ['user', 'policy', 'result']


class RoleFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Role
        fields = ['is_active']


class RoleAssignmentFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter()
    role = django_filters.UUIDFilter()
    scope = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = RoleAssignment
        fields = ['user', 'role', 'scope', 'is_active']


class PermissionFilter(django_filters.FilterSet):
    code = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Permission
        fields = ['is_active']


class RolePermissionFilter(django_filters.FilterSet):
    role = django_filters.UUIDFilter()
    permission = django_filters.UUIDFilter()

    class Meta:
        model = RolePermission
        fields = ['role', 'permission']
