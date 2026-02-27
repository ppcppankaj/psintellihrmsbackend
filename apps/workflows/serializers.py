"""
Workflow Serializers
"""

from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from apps.core.models import Organization
from apps.employees.models import Employee
from apps.employees.serializers import EmployeeListSerializer
from .models import WorkflowDefinition, WorkflowStep, WorkflowInstance, WorkflowAction
from .services import ENTITY_TYPE_CHOICES, EntityResolver, ActionPayload

class OrganizationScopedCreateMixin:
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            organization = request.user.get_organization()
            if not organization:
                raise serializers.ValidationError("User is not assigned to an organization.")
            validated_data['organization'] = organization
        return super().create(validated_data)


class WorkflowStepSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    class Meta:
        model = WorkflowStep
        fields = [
            'id', 'organization', 'workflow', 'order', 'name',
            'approver_type', 'approver_role', 'approver_user',
            'is_optional', 'can_delegate', 'sla_hours', 'escalate_to',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def validate(self, attrs):
        workflow = attrs.get('workflow')
        approver_user = attrs.get('approver_user')
        request = self.context.get('request')
        request_org = None
        if request and getattr(request, 'user', None) and request.user.is_authenticated:
            getter = getattr(request.user, 'get_organization', None)
            request_org = getter() if callable(getter) else None

        organization = (
            attrs.get('organization')
            or (workflow.organization if workflow else None)
            or request_org
        )

        if workflow and organization and workflow.organization_id != organization.id:
            raise serializers.ValidationError("Workflow and step must belong to the same organization.")

        if approver_user and organization and approver_user.organization_id != organization.id:
            raise serializers.ValidationError("Approver user must belong to the same organization.")

        if request_org and organization and request_org.id != organization.id:
            raise serializers.ValidationError("You cannot modify another organization's workflow step.")

        return attrs


class EscalateSerializer(serializers.Serializer):
    """Serializer for manual escalation"""
    reason = serializers.CharField(required=True, help_text="Reason for escalation")
    escalate_to = serializers.UUIDField(
        required=False, 
        allow_null=True,
        help_text="Optional specific employee to escalate to"
    )

class WorkflowDefinitionSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    steps = WorkflowStepSerializer(many=True, read_only=True, source='workflow_steps')
    
    class Meta:
        model = WorkflowDefinition
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'entity_type',
            'steps', 'conditions', 'sla_hours', 'auto_approve_on_sla',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

class WorkflowActionSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    actor_details = EmployeeListSerializer(source='actor', read_only=True)
    
    class Meta:
        model = WorkflowAction
        fields = [
            'id', 'organization', 'instance', 'step', 'actor', 'actor_details',
            'action', 'comments', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class WorkflowInstanceSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    """
    Enhanced serializer that provides fields expected by frontend ApprovalRequest type
    """
    actions = WorkflowActionSerializer(many=True, read_only=True)
    approver_details = EmployeeListSerializer(source='current_approver', read_only=True)
    workflow_name = serializers.ReadOnlyField(source='workflow.name')
    
    # Computed fields to match frontend ApprovalRequest interface
    request_type = serializers.SerializerMethodField()
    request_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    requester = serializers.SerializerMethodField()
    total_steps = serializers.SerializerMethodField()
    priority = serializers.SerializerMethodField()
    sla_deadline = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    steps = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowInstance
        fields = [
            'id', 'workflow', 'workflow_name', 'entity_type', 'entity_id',
            'current_step', 'status', 'started_at', 'completed_at',
            'current_approver', 'approver_details', 'actions', 'created_at', 'updated_at',
            # Computed fields for frontend compatibility
            'request_type', 'request_id', 'title', 'description', 'requester',
            'total_steps', 'priority', 'sla_deadline', 'is_overdue', 'steps'
        ]

    def validate(self, attrs):
        workflow = attrs.get('workflow') or getattr(self.instance, 'workflow', None)
        approver = attrs.get('current_approver') or getattr(self.instance, 'current_approver', None)
        request = self.context.get('request')
        request_org = None
        if request and getattr(request, 'user', None) and request.user.is_authenticated:
            getter = getattr(request.user, 'get_organization', None)
            request_org = getter() if callable(getter) else None

        organization = (
            attrs.get('organization')
            or getattr(self.instance, 'organization', None)
            or (workflow.organization if workflow else None)
            or request_org
        )

        if workflow and organization and workflow.organization_id != organization.id:
            raise serializers.ValidationError("Workflow and instance must belong to the same organization.")

        if approver and organization and approver.organization_id != organization.id:
            raise serializers.ValidationError("Workflow approver must belong to the same organization.")

        if request_org and organization and request_org.id != organization.id:
            raise serializers.ValidationError("You cannot operate on another organization's workflow instance.")

        return attrs
    
    def _get_entity(self, obj):
        """Fetch the actual entity (LeaveRequest, Expense, etc.)"""
        if not hasattr(obj, '_cached_entity'):
            obj._cached_entity = None
            try:
                resolved = EntityResolver.resolve(
                    organization_id=str(obj.organization_id),
                    entity_type=obj.entity_type,
                    entity_id=obj.entity_id,
                )
                obj._cached_entity = resolved.instance
            except ValidationError:
                obj._cached_entity = None
            except Exception:
                pass
        return obj._cached_entity
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_request_type(self, obj):
        """Map entity_type to frontend request_type"""
        type_map = {
            'leaverequest': 'leave',
            'expense': 'expense',
            'expenseclaim': 'expense',
            'attendance': 'attendance',
            'attendancecorrection': 'attendance',
            'resignation': 'resignation',
            'employeetransition': 'resignation',
        }
        return type_map.get(obj.entity_type, obj.entity_type)
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_request_id(self, obj):
        return str(obj.entity_id)
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_title(self, obj):
        """Generate a human-readable title"""
        entity = self._get_entity(obj)
        if entity:
            # Try to get title from entity
            if hasattr(entity, 'title'):
                return entity.title
            if hasattr(entity, 'leave_type') and hasattr(entity, 'employee'):
                return f"{entity.leave_type.name} - {entity.employee.full_name}"
            if hasattr(entity, 'description'):
                return entity.description[:50] if entity.description else 'No description'
        return f"{obj.entity_type.replace('_', ' ').title()} Request"
    
    @extend_schema_field({'type': 'string', 'nullable': True})
    def get_description(self, obj):
        entity = self._get_entity(obj)
        if entity and hasattr(entity, 'reason'):
            return entity.reason
        return None
    
    @extend_schema_field({'type': 'object', 'nullable': True, 'properties': {'id': {'type': 'string'}, 'employee_id': {'type': 'string'}, 'full_name': {'type': 'string'}, 'avatar': {'type': 'string', 'nullable': True}, 'department': {'type': 'string'}, 'designation': {'type': 'string'}}})
    def get_requester(self, obj):
        """Get the requester (employee who initiated the request)"""
        entity = self._get_entity(obj)
        employee = None
        
        if entity:
            # Try common patterns for getting employee
            if hasattr(entity, 'employee'):
                employee = entity.employee
            elif hasattr(entity, 'submitted_by'):
                employee = entity.submitted_by
            elif hasattr(entity, 'user'):
                from apps.employees.models import Employee
                employee = Employee.objects.filter(
                    user=entity.user,
                    organization=obj.organization
                ).first()
        
        if employee:
            return {
                'id': str(employee.id),
                'employee_id': employee.employee_id or '',
                'full_name': employee.full_name,
                'avatar': employee.avatar.url if employee.avatar else None,
                'department': employee.department.name if employee.department else '',
                'designation': employee.designation.name if employee.designation else '',
            }
        return None
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_total_steps(self, obj):
        if obj.workflow:
            return obj.workflow.workflow_steps.count()
        return 1
    
    @extend_schema_field({'type': 'string', 'enum': ['normal', 'urgent', 'high', 'low']})
    def get_priority(self, obj):
        """Determine priority based on SLA or entity urgency"""
        entity = self._get_entity(obj)
        if entity and hasattr(entity, 'priority'):
            return entity.priority
        # Default based on overdue status
        if self.get_is_overdue(obj):
            return 'urgent'
        return 'normal'
    
    @extend_schema_field({'type': 'string', 'format': 'date-time', 'nullable': True})
    def get_sla_deadline(self, obj):
        if obj.workflow and obj.workflow.sla_hours:
            from datetime import timedelta
            deadline = obj.started_at + timedelta(hours=obj.workflow.sla_hours)
            return deadline.isoformat()
        return None
    
    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_overdue(self, obj):
        if obj.workflow and obj.workflow.sla_hours:
            from datetime import timedelta
            deadline = obj.started_at + timedelta(hours=obj.workflow.sla_hours)
            return timezone.now() > deadline and obj.status == 'in_progress'
        return False
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_steps(self, obj):
        """Get workflow steps with status"""
        if not obj.workflow:
            return []
        
        steps = obj.workflow.workflow_steps.all().order_by('order')
        actions_by_step = {a.step: a for a in obj.actions.all()}
        
        result = []
        for step in steps:
            action = actions_by_step.get(step.order)
            result.append({
                'id': str(step.id),
                'order': step.order,
                'name': step.name,
                'approver_type': step.approver_type,
                'approver_role': {'id': str(step.approver_role.id), 'name': step.approver_role.name} if step.approver_role else None,
                'approver_user': {'id': str(step.approver_user.id), 'full_name': step.approver_user.full_name} if step.approver_user else None,
                'status': action.action if action else ('pending' if step.order >= obj.current_step else 'skipped'),
                'completed_at': action.created_at.isoformat() if action else None,
                'completed_by': {'id': str(action.actor.id), 'full_name': action.actor.full_name} if action and action.actor else None,
                'comments': action.comments if action else None,
            })
        return result


class WorkflowStartSerializer(serializers.Serializer):
    """Tenant-safe payload for starting workflow instances."""

    entity_type = serializers.ChoiceField(choices=ENTITY_TYPE_CHOICES)
    entity_id = serializers.CharField()
    workflow_code = serializers.CharField(required=False, allow_blank=True)
    organization_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        organization = self._resolve_organization(attrs.get('organization_id'))
        attrs['organization'] = organization
        try:
            resolved = EntityResolver.resolve(
                organization_id=str(organization.id),
                entity_type=attrs['entity_type'],
                entity_id=attrs['entity_id'],
            )
        except ValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or {'entity_type': exc.messages}
            raise serializers.ValidationError(detail)
        attrs['resolved_entity'] = resolved
        return attrs

    def _resolve_organization(self, override_id):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        organization = None
        if user and user.is_authenticated and hasattr(user, 'get_organization'):
            organization = user.get_organization()

        if override_id:
            override_id = str(override_id)
            if organization and str(organization.id) != override_id and not (user and user.is_superuser):
                raise serializers.ValidationError({'organization_id': 'Cannot override organization context'})
            try:
                organization = Organization.objects.get(id=override_id)
            except Organization.DoesNotExist:
                raise serializers.ValidationError({'organization_id': 'Organization not found'})

        if not organization:
            raise serializers.ValidationError({'organization_id': 'Organization context is required'})
        return organization


class WorkflowActionRequestSerializer(serializers.Serializer):
    """Serializer that normalizes workflow action payloads."""

    ACTION_CHOICES = (
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('forward', 'Forward'),
        ('delegate', 'Delegate'),
    )

    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    comments = serializers.CharField(required=False, allow_blank=True)
    forward_to = serializers.UUIDField(required=False, allow_null=True)
    delegate_to = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        action = attrs['action']
        if action == 'reject' and not attrs.get('comments'):
            raise serializers.ValidationError({'comments': 'Comments required when rejecting'})

        attrs['forward_to_employee'] = None
        attrs['delegate_to_employee'] = None

        if action == 'forward':
            attrs['forward_to_employee'] = self._resolve_employee(attrs.get('forward_to'), 'forward_to')
            if attrs['forward_to_employee'] is None:
                raise serializers.ValidationError({'forward_to': 'Forward action requires target employee'})

        if action == 'delegate':
            attrs['delegate_to_employee'] = self._resolve_employee(attrs.get('delegate_to'), 'delegate_to')
            if attrs['delegate_to_employee'] is None:
                raise serializers.ValidationError({'delegate_to': 'Delegate action requires target employee'})

        return attrs

    def _resolve_employee(self, employee_id, field_name):
        if not employee_id:
            return None
        organization = self.context.get('organization')
        if not organization:
            raise serializers.ValidationError({field_name: 'Organization context is required'})
        try:
            employee = Employee.objects.get(id=employee_id, organization=organization)
        except Employee.DoesNotExist:
            raise serializers.ValidationError({field_name: 'Employee not found in organization'})

        branch_ids = self.context.get('branch_ids')
        if branch_ids and employee.branch_id not in branch_ids:
            raise serializers.ValidationError({field_name: 'Employee outside your branch scope'})
        return employee

    def to_action_payload(self) -> ActionPayload:
        if not hasattr(self, 'validated_data'):
            raise RuntimeError('Serializer must be validated before building payload')
        return ActionPayload(
            action=self.validated_data['action'],
            comments=self.validated_data.get('comments', ''),
            forward_to=self.validated_data.get('forward_to_employee'),
            delegate_to=self.validated_data.get('delegate_to_employee'),
        )
