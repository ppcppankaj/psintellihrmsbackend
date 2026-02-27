"""
Performance Serializers
"""

from rest_framework import serializers
from .models import (
    PerformanceCycle, OKRObjective, KeyResult, PerformanceReview, ReviewFeedback,
    KeyResultArea, EmployeeKRA, KPI, Competency, EmployeeCompetency, TrainingRecommendation
)
from apps.employees.serializers import EmployeeListSerializer


class PerformanceCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceCycle
        fields = [
            'id', 'organization', 'name', 'year', 'start_date', 'end_date',
            'goal_setting_start', 'goal_setting_end', 'review_start', 'review_end',
            'status', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class KeyResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeyResult
        fields = [
            'id', 'organization', 'objective', 'title', 'description',
            'metric_type', 'target_value', 'current_value', 'weight', 'progress',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class OKRObjectiveSerializer(serializers.ModelSerializer):
    key_results = KeyResultSerializer(many=True, read_only=True)
    employee_details = EmployeeListSerializer(source='employee', read_only=True)
    
    class Meta:
        model = OKRObjective
        fields = [
            'id', 'organization', 'cycle', 'employee', 'employee_details',
            'parent', 'title', 'description', 'weight', 'status', 'progress',
            'key_results', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class ReviewFeedbackSerializer(serializers.ModelSerializer):
    reviewer_details = EmployeeListSerializer(source='reviewer', read_only=True)
    
    class Meta:
        model = ReviewFeedback
        fields = [
            'id', 'organization', 'review', 'reviewer', 'reviewer_details',
            'relationship', 'rating', 'feedback', 'is_anonymous',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class PerformanceReviewSerializer(serializers.ModelSerializer):
    employee_details = EmployeeListSerializer(source='employee', read_only=True)
    cycle_details = PerformanceCycleSerializer(source='cycle', read_only=True)
    feedbacks = ReviewFeedbackSerializer(many=True, read_only=True)
    
    class Meta:
        model = PerformanceReview
        fields = [
            'id', 'organization', 'cycle', 'cycle_details', 'employee', 'employee_details',
            'self_rating', 'self_comments', 'manager_rating', 'manager_comments',
            'final_rating', 'status', 'feedbacks', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class KeyResultAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeyResultArea
        fields = [
            'id', 'organization', 'name', 'code', 'description',
            'designation', 'department', 'default_weightage',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class EmployeeKRASerializer(serializers.ModelSerializer):
    kra_details = KeyResultAreaSerializer(source='kra', read_only=True)
    employee_details = EmployeeListSerializer(source='employee', read_only=True)
    
    class Meta:
        model = EmployeeKRA
        fields = [
            'id', 'organization', 'employee', 'employee_details', 'cycle', 'kra', 'kra_details',
            'weightage', 'target', 'achievement',
            'self_rating', 'manager_rating', 'final_rating', 'comments',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class KPISerializer(serializers.ModelSerializer):
    class Meta:
        model = KPI
        fields = [
            'id', 'organization', 'employee_kra', 'employee', 'name', 'description',
            'metric_type', 'measurement_frequency',
            'target_value', 'threshold_value', 'stretch_value', 'current_value',
            'period_start', 'period_end', 'is_achieved', 'achievement_percentage',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class CompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Competency
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'category',
            'level_1_description', 'level_2_description', 'level_3_description',
            'level_4_description', 'level_5_description',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class EmployeeCompetencySerializer(serializers.ModelSerializer):
    competency_details = CompetencySerializer(source='competency', read_only=True)
    
    class Meta:
        model = EmployeeCompetency
        fields = [
            'id', 'organization', 'employee', 'competency', 'competency_details', 'cycle',
            'expected_level', 'self_assessed_level', 'manager_assessed_level', 'final_level',
            'gap', 'comments', 'development_plan',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class TrainingRecommendationSerializer(serializers.ModelSerializer):
    competency_details = CompetencySerializer(source='competency', read_only=True)
    
    class Meta:
        model = TrainingRecommendation
        fields = [
            'id', 'organization', 'employee', 'competency', 'competency_details', 'cycle',
            'suggested_training', 'priority', 'is_completed', 'completion_date', 'notes',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
