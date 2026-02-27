"""
ABAC Models - Attribute-Based Access Control
Policy-based access control using subject, resource, action, and environment attributes
"""

import uuid
import json
import re
from operator import eq, ne, gt, ge, lt, le
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import OrganizationEntity


class AttributeType(OrganizationEntity):
    """
    Defines types of attributes that can be used in policies.
    E.g., department, location, employment_status, job_level, etc.
    """
    
    # Attribute categories
    SUBJECT = 'subject'  # User attributes
    RESOURCE = 'resource'  # Resource/object attributes
    ACTION = 'action'  # Action/operation being performed
    ENVIRONMENT = 'environment'  # Context (time, location, IP, etc.)
    
    CATEGORIES = [
        (SUBJECT, 'Subject Attribute'),
        (RESOURCE, 'Resource Attribute'),
        (ACTION, 'Action Attribute'),
        (ENVIRONMENT, 'Environment Attribute'),
    ]
    
    # Data types
    STRING = 'string'
    NUMBER = 'number'
    BOOLEAN = 'boolean'
    DATE = 'date'
    TIME = 'time'
    LIST = 'list'
    
    DATA_TYPES = [
        (STRING, 'String'),
        (NUMBER, 'Number'),
        (BOOLEAN, 'Boolean'),
        (DATE, 'Date'),
        (TIME, 'Time'),
        (LIST, 'List'),
    ]
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100, db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    data_type = models.CharField(max_length=20, choices=DATA_TYPES, default=STRING)
    description = models.TextField(blank=True)
    
    # For validation
    allowed_values = models.JSONField(null=True, blank=True)  # List of allowed values
    
    class Meta:
        ordering = ['category', 'name']
        unique_together = ['organization', 'code']
    
    def __str__(self):
        return f"{self.name} ({self.category})"


class Policy(OrganizationEntity):
    """
    ABAC Policy definition.
    Combines multiple rules to determine access permissions.
    """
    
    # Effect types
    ALLOW = 'allow'
    DENY = 'deny'
    
    EFFECTS = [
        (ALLOW, 'Allow'),
        (DENY, 'Deny'),
    ]
    
    # Policy types
    GENERAL = 'general'
    MODULE = 'module'
    API = 'api'
    DATA = 'data'
    
    POLICY_TYPES = [
        (GENERAL, 'General Access'),
        (MODULE, 'Module Access'),
        (API, 'API Endpoint'),
        (DATA, 'Data/Field Access'),
    ]
    
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True)
    
    policy_type = models.CharField(max_length=20, choices=POLICY_TYPES, default=GENERAL)
    effect = models.CharField(max_length=10, choices=EFFECTS, default=ALLOW)
    
    # Priority (higher = evaluated first, for conflict resolution)
    priority = models.IntegerField(default=0)
    
    # Target resource
    resource_type = models.CharField(max_length=100, blank=True)  # e.g., 'employee', 'payroll'
    resource_id = models.CharField(max_length=100, blank=True)  # Optional specific resource ID
    
    # Target actions
    actions = models.JSONField(default=list)  # List of allowed actions: ['view', 'create', 'update']
    
    # Combine logic for rules
    COMBINE_AND = 'and'
    COMBINE_OR = 'or'
    
    COMBINE_LOGICS = [
        (COMBINE_AND, 'AND - All rules must match'),
        (COMBINE_OR, 'OR - Any rule can match'),
    ]
    
    combine_logic = models.CharField(max_length=10, choices=COMBINE_LOGICS, default=COMBINE_AND)
    
    # Validity period
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-priority', 'name']
        verbose_name_plural = 'Policies'
        unique_together = ['organization', 'code']
    
    def __str__(self):
        return self.name
    
    def is_valid_now(self):
        """Check if policy is currently valid"""
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True
    
    def evaluate(self, subject_attrs, resource_attrs, action, environment_attrs):
        """
        Evaluate this policy against provided attributes.
        Returns True if policy grants access, False otherwise.
        """
        if not self.is_active or not self.is_valid_now():
            return False
        
        # Check if action matches
        if self.actions and action not in self.actions:
            return False
        
        # Evaluate all rules
        rules = self.rules.filter(is_active=True)
        if not rules.exists():
            return self.effect == self.ALLOW
        
        rule_results = [rule.evaluate(subject_attrs, resource_attrs, environment_attrs) 
                       for rule in rules]
        
        if self.combine_logic == self.COMBINE_AND:
            matches = all(rule_results)
        else:  # OR
            matches = any(rule_results)
        
        if matches:
            return self.effect == self.ALLOW
        return False


class PolicyRule(OrganizationEntity):
    """
    Individual rule within a policy.
    Defines conditions that must be met for the rule to match.
    """
    
    # Operators
    EQUALS = 'eq'
    NOT_EQUALS = 'neq'
    GREATER_THAN = 'gt'
    GREATER_THAN_EQUAL = 'gte'
    LESS_THAN = 'lt'
    LESS_THAN_EQUAL = 'lte'
    IN = 'in'
    NOT_IN = 'not_in'
    CONTAINS = 'contains'
    NOT_CONTAINS = 'not_contains'
    STARTS_WITH = 'starts_with'
    ENDS_WITH = 'ends_with'
    REGEX = 'regex'
    
    OPERATORS = [
        (EQUALS, 'Equals'),
        (NOT_EQUALS, 'Not Equals'),
        (GREATER_THAN, 'Greater Than'),
        (GREATER_THAN_EQUAL, 'Greater Than or Equal'),
        (LESS_THAN, 'Less Than'),
        (LESS_THAN_EQUAL, 'Less Than or Equal'),
        (IN, 'In List'),
        (NOT_IN, 'Not In List'),
        (CONTAINS, 'Contains'),
        (NOT_CONTAINS, 'Does Not Contain'),
        (STARTS_WITH, 'Starts With'),
        (ENDS_WITH, 'Ends With'),
        (REGEX, 'Regex Match'),
    ]
    
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='rules')
    
    # Attribute to check
    attribute_type = models.ForeignKey(AttributeType, on_delete=models.CASCADE)
    attribute_path = models.CharField(max_length=255)  # e.g., 'user.department.name', 'resource.confidential'
    
    # Comparison
    operator = models.CharField(max_length=20, choices=OPERATORS, default=EQUALS)
    value = models.JSONField()  # Value to compare against (can be string, number, list, etc.)
    
    # Negate this rule
    negate = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['policy', 'id']
    
    def __str__(self):
        return f"{self.attribute_path} {self.operator} {self.value}"
    
    def evaluate(self, subject_attrs, resource_attrs, environment_attrs):
        """
        Evaluate this rule against provided attributes.
        Returns True if the rule matches, False otherwise.
        """
        # Get the attribute value based on category
        if self.attribute_type.category == AttributeType.SUBJECT:
            attr_dict = subject_attrs
        elif self.attribute_type.category == AttributeType.RESOURCE:
            attr_dict = resource_attrs
        elif self.attribute_type.category == AttributeType.ENVIRONMENT:
            attr_dict = environment_attrs
        else:
            return False
        
        # Navigate attribute path
        attr_value = attr_dict
        for part in self.attribute_path.split('.'):
            if isinstance(attr_value, dict):
                attr_value = attr_value.get(part)
            elif hasattr(attr_value, part):
                attr_value = getattr(attr_value, part)
            else:
                return False
        
        # Handle callable (methods)
        if callable(attr_value):
            attr_value = attr_value()
        
        # Evaluate based on operator
        result = False
        try:
            if self.operator == self.EQUALS:
                result = eq(attr_value, self.value)
            elif self.operator == self.NOT_EQUALS:
                result = ne(attr_value, self.value)
            elif self.operator == self.GREATER_THAN:
                result = gt(attr_value, self.value)
            elif self.operator == self.GREATER_THAN_EQUAL:
                result = ge(attr_value, self.value)
            elif self.operator == self.LESS_THAN:
                result = lt(attr_value, self.value)
            elif self.operator == self.LESS_THAN_EQUAL:
                result = le(attr_value, self.value)
            elif self.operator == self.IN:
                result = attr_value in self.value
            elif self.operator == self.NOT_IN:
                result = attr_value not in self.value
            elif self.operator == self.CONTAINS:
                result = self.value in str(attr_value)
            elif self.operator == self.NOT_CONTAINS:
                result = self.value not in str(attr_value)
            elif self.operator == self.STARTS_WITH:
                result = str(attr_value).startswith(str(self.value))
            elif self.operator == self.ENDS_WITH:
                result = str(attr_value).endswith(str(self.value))
            elif self.operator == self.REGEX:
                result = bool(re.match(self.value, str(attr_value)))
        except (TypeError, ValueError, AttributeError):
            result = False
        
        # Apply negation if specified
        if self.negate:
            result = not result
        
        return result

    def clean(self):
        super().clean()
        if self.policy_id and self.organization_id:
            if self.policy.organization_id != self.organization_id:
                raise ValidationError('PolicyRule must belong to the same organization as its policy.')

    def save(self, *args, **kwargs):
        if self.policy_id:
            self.organization = self.policy.organization
        self.clean()
        super().save(*args, **kwargs)


class UserPolicy(OrganizationEntity):
    """
    Assigns policies to specific users.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_policies')
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='user_assignments')
    
    # Override policy priority for this user
    priority_override = models.IntegerField(null=True, blank=True)
    
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='policies_assigned')
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    # Validity period (can override policy's validity)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['user', 'policy']
        ordering = ['-priority_override', '-assigned_at']
    
    def __str__(self):
        return f"{self.user} - {self.policy}"
    
    def is_valid_now(self):
        """Check if assignment is currently valid"""
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True


class GroupPolicy(OrganizationEntity):
    """
    Assigns policies to groups of users (e.g., department, location).
    """
    
    GROUP_TYPES = [
        ('department', 'Department'),
        ('location', 'Location'),
        ('job_level', 'Job Level'),
        ('employment_type', 'Employment Type'),
        ('custom', 'Custom Group'),
    ]
    
    name = models.CharField(max_length=200)
    group_type = models.CharField(max_length=50, choices=GROUP_TYPES)
    group_value = models.CharField(max_length=200)  # e.g., 'HR', 'Manager', 'New York'
    
    policies = models.ManyToManyField(Policy, related_name='group_assignments')
    
    class Meta:
        unique_together = ['organization', 'group_type', 'group_value']
        ordering = ['group_type', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.group_type})"


class PolicyLog(OrganizationEntity):
    """
    Audit log for policy evaluations (for debugging and compliance).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='policy_logs')
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, null=True, related_name='evaluation_logs')
    
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=50)
    
    result = models.BooleanField()  # True = access granted, False = denied
    evaluated_at = models.DateTimeField(auto_now_add=True)
    
    # Context
    subject_attributes = models.JSONField(default=dict)
    resource_attributes = models.JSONField(default=dict)
    environment_attributes = models.JSONField(default=dict)
    
    # Evaluation details
    policies_evaluated = models.JSONField(default=list)  # List of policy IDs evaluated
    decision_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-evaluated_at']
        indexes = [
            models.Index(fields=['user', '-evaluated_at']),
            models.Index(fields=['resource_type', 'action', '-evaluated_at']),
        ]
    
    def __str__(self):
        status = "GRANTED" if self.result else "DENIED"
        return f"{self.user} - {self.action} on {self.resource_type} - {status}"


# Legacy compatibility models (minimal for backward compatibility)
class Role(OrganizationEntity):
    """
    Legacy Role model - kept for backward compatibility during migration.
    Maps to ABAC policies internally.
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)
    
    # Maps to a set of policies
    policies = models.ManyToManyField(Policy, related_name='legacy_roles', blank=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['organization', 'code']
    
    def __str__(self):
        return self.name


class RoleAssignment(OrganizationEntity):
    """
    Role Assignment model - assigns roles to users with scope.
    
    This is the primary model for RBAC role assignments.
    Supports scoped assignments (organization, branch, department level).
    """
    
    # Scope choices
    SCOPE_GLOBAL = 'global'
    SCOPE_ORGANIZATION = 'organization'
    SCOPE_BRANCH = 'branch'
    SCOPE_DEPARTMENT = 'department'
    
    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, 'Global'),
        (SCOPE_ORGANIZATION, 'Organization'),
        (SCOPE_BRANCH, 'Branch'),
        (SCOPE_DEPARTMENT, 'Department'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='user_roles',
        db_index=True
    )
    role = models.ForeignKey(
        Role, 
        on_delete=models.CASCADE, 
        related_name='role_assignments',
        db_index=True
    )
    
    # Scope of the role assignment
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ORGANIZATION)
    scope_id = models.UUIDField(null=True, blank=True, db_index=True)  # ID of the scope entity
    
    # Validity period
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    # Audit
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='assigned_roles'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'role', 'scope', 'scope_id']
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['role', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.role.name} ({self.scope})"
    
    def is_valid_now(self):
        """Check if assignment is currently valid"""
        from django.utils import timezone
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def clean(self):
        super().clean()
        if self.scope == self.SCOPE_ORGANIZATION:
            if not self.organization_id:
                raise ValidationError('Organization scoped roles require an organization.')
            if self.scope_id and str(self.scope_id) != str(self.organization_id):
                raise ValidationError('scope_id must match organization for organization scoped roles.')
            self.scope_id = self.organization_id

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class UserRole(OrganizationEntity):
    """
    Legacy UserRole model - DEPRECATED, use RoleAssignment instead.
    Kept for backward compatibility during migration.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='legacy_user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='legacy_role_assignments')
    
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'role']
    
    def __str__(self):
        return f"{self.user} - {self.role}"


# Stub models for backward compatibility
class Permission(OrganizationEntity):
    """Legacy Permission model stub"""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    module = models.CharField(max_length=50, db_index=True)
    action = models.CharField(max_length=50, db_index=True, null=True, blank=True)
    permission_type = models.CharField(max_length=50, db_index=True, default='module')
    
    class Meta:
        ordering = ['module', 'name']
        unique_together = ['organization', 'code']
    
    def __str__(self):
        return f"{self.module}.{self.code}"


class RolePermission(OrganizationEntity):
    """Legacy RolePermission stub"""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['role', 'permission']
    
    def __str__(self):
        return f"{self.role.name} - {self.permission.code}"
