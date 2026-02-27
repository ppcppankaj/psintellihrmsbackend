"""Training Admin"""
from django.contrib import admin
from .models import (
    TrainingCategory,
    TrainingProgram,
    TrainingMaterial,
    TrainingEnrollment,
    TrainingCompletion,
)


@admin.register(TrainingCategory)
class TrainingCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    search_fields = ['name', 'code']
    list_filter = ['is_active']


@admin.register(TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'status', 'is_mandatory', 'start_date', 'end_date']
    search_fields = ['name', 'code']
    list_filter = ['status', 'is_mandatory', 'delivery_mode']


@admin.register(TrainingMaterial)
class TrainingMaterialAdmin(admin.ModelAdmin):
    list_display = ['title', 'program', 'material_type', 'is_required', 'order']
    list_filter = ['material_type', 'is_required']
    search_fields = ['title', 'program__name']


@admin.register(TrainingEnrollment)
class TrainingEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['program', 'employee', 'status', 'enrolled_at', 'completed_at']
    list_filter = ['status']
    search_fields = ['program__name', 'employee__user__first_name', 'employee__user__last_name']


@admin.register(TrainingCompletion)
class TrainingCompletionAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'completed_at', 'score']
    search_fields = ['enrollment__program__name', 'enrollment__employee__user__first_name']
