"""Training Serializers"""
from rest_framework import serializers
from .models import (
    TrainingCategory,
    TrainingProgram,
    TrainingMaterial,
    TrainingEnrollment,
    TrainingCompletion,
)


class TrainingCategorySerializer(serializers.ModelSerializer):
    program_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TrainingCategory
        fields = [
            'id', 'name', 'code', 'description', 'display_order',
            'is_active', 'created_at', 'updated_at', 'program_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'program_count']


class TrainingProgramSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    enrollment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TrainingProgram
        fields = [
            'id', 'category', 'category_name', 'name', 'code', 'description',
            'provider', 'delivery_mode', 'location', 'start_date', 'end_date',
            'enrollment_deadline', 'duration_hours', 'capacity',
            'is_mandatory', 'status', 'status_display',
            'prerequisites', 'tags', 'metadata',
            'is_active', 'created_at', 'updated_at', 'enrollment_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status_display', 'enrollment_count']


class TrainingMaterialSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source='program.name', read_only=True)
    material_type_display = serializers.CharField(source='get_material_type_display', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True, allow_null=True)

    class Meta:
        model = TrainingMaterial
        fields = [
            'id', 'program', 'program_name', 'title', 'description',
            'material_type', 'material_type_display', 'file', 'url', 'order',
            'is_required', 'uploaded_by', 'uploaded_by_name',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'uploaded_by_name', 'material_type_display']


class TrainingEnrollmentSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source='program.name', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TrainingEnrollment
        fields = [
            'id', 'program', 'program_name', 'employee', 'employee_name',
            'assigned_by', 'status', 'status_display',
            'enrolled_at', 'started_at', 'completed_at', 'due_date',
            'progress_percent', 'score', 'certificate_file',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'enrolled_at', 'started_at', 'completed_at',
            'created_at', 'updated_at', 'status_display'
        ]


class TrainingCompletionSerializer(serializers.ModelSerializer):
    enrollment_id = serializers.UUIDField(source='enrollment.id', read_only=True)
    program_name = serializers.CharField(source='enrollment.program.name', read_only=True)
    employee_name = serializers.CharField(source='enrollment.employee.full_name', read_only=True)

    class Meta:
        model = TrainingCompletion
        fields = [
            'id', 'enrollment', 'enrollment_id', 'program_name', 'employee_name',
            'completed_at', 'score', 'feedback', 'certificate_file',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'completed_at', 'created_at', 'updated_at']
