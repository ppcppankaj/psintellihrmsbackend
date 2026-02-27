"""Onboarding Serializers"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from apps.core.upload_validators import validate_upload as _validate_upload
from .models import (
    OnboardingTemplate, OnboardingTaskTemplate,
    EmployeeOnboarding, OnboardingTaskProgress, OnboardingDocument
)


class OnboardingTaskTemplateSerializer(serializers.ModelSerializer):
    """Serializer for onboarding task templates"""
    assigned_to_type_display = serializers.CharField(
        source='get_assigned_to_type_display', read_only=True
    )
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    
    class Meta:
        model = OnboardingTaskTemplate
        fields = [
            'id', 'title', 'description', 'stage', 'stage_display',
            'assigned_to_type', 'assigned_to_type_display', 'assigned_to_role',
            'due_days_offset', 'is_mandatory', 'requires_attachment',
            'requires_acknowledgement', 'depends_on', 'order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['depends_on'].queryset = OnboardingTaskTemplate.objects.filter(
                organization=request.organization
            )
            # assigned_to_role is from abac - roles are often global but can be tenant-specific
            # if they are OrganizationEntity, they should be filtered.
            # Assuming Role is organization-scoped based on previous audit.
            from apps.abac.models import Role
            self.fields['assigned_to_role'].queryset = Role.objects.filter(
                organization=request.organization
            )


class OnboardingTemplateListSerializer(serializers.ModelSerializer):
    """List serializer for onboarding templates"""
    department_name = serializers.CharField(source='department.name', read_only=True, allow_null=True)
    designation_name = serializers.CharField(source='designation.name', read_only=True, allow_null=True)
    task_count = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingTemplate
        fields = [
            'id', 'name', 'code', 'description',
            'department', 'department_name', 'designation', 'designation_name',
            'days_before_joining', 'days_to_complete',
            'is_default', 'is_active', 'task_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            from apps.employees.models import Department, Designation
            self.fields['department'].queryset = Department.objects.filter(
                organization=request.organization
            )
            self.fields['designation'].queryset = Designation.objects.filter(
                organization=request.organization
            )
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_task_count(self, obj):
        return obj.tasks.count()


class OnboardingTemplateDetailSerializer(OnboardingTemplateListSerializer):
    """Detail serializer with nested tasks"""
    tasks = OnboardingTaskTemplateSerializer(many=True, read_only=True)
    
    class Meta(OnboardingTemplateListSerializer.Meta):
        fields = OnboardingTemplateListSerializer.Meta.fields + ['tasks']


class OnboardingDocumentSerializer(serializers.ModelSerializer):
    """Serializer for onboarding documents"""
    document_type_display = serializers.CharField(
        source='get_document_type_display', read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    verified_by_name = serializers.CharField(
        source='verified_by.full_name', read_only=True, allow_null=True
    )
    
    class Meta:
        model = OnboardingDocument
        fields = [
            'id', 'document_type', 'document_type_display', 'document_name',
            'file', 'file_size', 'is_mandatory', 'status', 'status_display',
            'verified_by', 'verified_by_name', 'verified_at', 'rejection_reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file_size', 'verified_by', 'verified_at', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            from apps.employees.models import Employee
            self.fields['verified_by'].queryset = Employee.objects.filter(
                organization=request.organization
            )


class OnboardingTaskProgressSerializer(serializers.ModelSerializer):
    """Serializer for task progress"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assigned_to_name = serializers.CharField(
        source='assigned_to.full_name', read_only=True, allow_null=True
    )
    completed_by_name = serializers.CharField(
        source='completed_by.full_name', read_only=True, allow_null=True
    )
    is_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingTaskProgress
        fields = [
            'id', 'title', 'description', 'stage', 'is_mandatory',
            'assigned_to', 'assigned_to_name', 'due_date',
            'status', 'status_display', 'is_overdue',
            'started_at', 'completed_at', 'completed_by', 'completed_by_name',
            'notes', 'attachment', 'acknowledged',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'title', 'description', 'stage', 'is_mandatory',
            'due_date', 'task_template', 'created_at', 'updated_at'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            from apps.employees.models import Employee
            self.fields['assigned_to'].queryset = Employee.objects.filter(
                organization=request.organization
            )
            self.fields['completed_by'].queryset = Employee.objects.filter(
                organization=request.organization
            )
    
    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_overdue(self, obj):
        from django.utils import timezone
        if obj.status in ['completed', 'skipped']:
            return False
        return obj.due_date < timezone.now().date()


class EmployeeOnboardingListSerializer(serializers.ModelSerializer):
    """List serializer for employee onboarding"""
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    hr_responsible_name = serializers.CharField(
        source='hr_responsible.full_name', read_only=True, allow_null=True
    )
    buddy_name = serializers.CharField(source='buddy.full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = EmployeeOnboarding
        fields = [
            'id', 'employee', 'employee_id', 'employee_name',
            'template', 'template_name',
            'joining_date', 'start_date', 'target_completion_date', 'actual_completion_date',
            'status', 'status_display',
            'total_tasks', 'completed_tasks', 'progress_percentage',
            'hr_responsible', 'hr_responsible_name',
            'buddy', 'buddy_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_tasks', 'completed_tasks', 'progress_percentage',
            'created_at', 'updated_at'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            from apps.employees.models import Employee
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )
            self.fields['template'].queryset = OnboardingTemplate.objects.filter(
                organization=request.organization
            )
            self.fields['hr_responsible'].queryset = Employee.objects.filter(
                organization=request.organization
            )
            self.fields['buddy'].queryset = Employee.objects.filter(
                organization=request.organization
            )


class EmployeeOnboardingDetailSerializer(EmployeeOnboardingListSerializer):
    """Detail serializer with nested tasks and documents"""
    task_progress = OnboardingTaskProgressSerializer(many=True, read_only=True)
    documents = OnboardingDocumentSerializer(many=True, read_only=True)
    
    class Meta(EmployeeOnboardingListSerializer.Meta):
        fields = EmployeeOnboardingListSerializer.Meta.fields + ['task_progress', 'documents', 'notes']


class InitiateOnboardingSerializer(serializers.Serializer):
    """Serializer for initiating employee onboarding"""
    employee_id = serializers.UUIDField()
    template_id = serializers.UUIDField(required=False, allow_null=True)
    joining_date = serializers.DateField()
    hr_responsible_id = serializers.UUIDField(required=False, allow_null=True)
    buddy_id = serializers.UUIDField(required=False, allow_null=True)


class CompleteTaskSerializer(serializers.Serializer):
    """Serializer for completing an onboarding task"""
    notes = serializers.CharField(required=False, allow_blank=True)
    attachment = serializers.FileField(required=False, allow_null=True, validators=[_validate_upload])
    acknowledged = serializers.BooleanField(default=True)


class VerifyDocumentSerializer(serializers.Serializer):
    """Serializer for verifying/rejecting documents"""
    action = serializers.ChoiceField(choices=['verify', 'reject'])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
