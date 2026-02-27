"""Onboarding Admin Configuration"""

from django.contrib import admin
from .models import (
    OnboardingTemplate, OnboardingTaskTemplate,
    EmployeeOnboarding, OnboardingTaskProgress, OnboardingDocument
)


class OnboardingTaskTemplateInline(admin.TabularInline):
    model = OnboardingTaskTemplate
    extra = 1
    fields = ['title', 'stage', 'assigned_to_type', 'due_days_offset', 'is_mandatory', 'order']
    ordering = ['stage', 'order']


@admin.register(OnboardingTemplate)
class OnboardingTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'department', 'designation', 'is_default', 'is_active']
    list_filter = ['is_active', 'is_default', 'department']
    search_fields = ['name', 'code']
    inlines = [OnboardingTaskTemplateInline]


@admin.register(OnboardingTaskTemplate)
class OnboardingTaskTemplateAdmin(admin.ModelAdmin):
    list_display = ['title', 'template', 'stage', 'assigned_to_type', 'due_days_offset', 'is_mandatory']
    list_filter = ['template', 'stage', 'assigned_to_type', 'is_mandatory']
    search_fields = ['title', 'description']
    ordering = ['template', 'stage', 'order']


class OnboardingTaskProgressInline(admin.TabularInline):
    model = OnboardingTaskProgress
    extra = 0
    fields = ['title', 'stage', 'assigned_to', 'due_date', 'status']
    readonly_fields = ['title', 'stage', 'due_date']
    can_delete = False


class OnboardingDocumentInline(admin.TabularInline):
    model = OnboardingDocument
    extra = 0
    fields = ['document_type', 'document_name', 'file', 'status', 'verified_by']
    readonly_fields = ['verified_by']


@admin.register(EmployeeOnboarding)
class EmployeeOnboardingAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'template', 'joining_date', 'status',
        'progress_percentage', 'hr_responsible'
    ]
    list_filter = ['status', 'template', 'joining_date']
    search_fields = ['employee__employee_id', 'employee__user__first_name', 'employee__user__last_name']
    readonly_fields = ['total_tasks', 'completed_tasks', 'progress_percentage']
    inlines = [OnboardingTaskProgressInline, OnboardingDocumentInline]
    
    fieldsets = (
        ('Employee Info', {
            'fields': ('employee', 'template')
        }),
        ('Dates', {
            'fields': ('joining_date', 'start_date', 'target_completion_date', 'actual_completion_date')
        }),
        ('Status', {
            'fields': ('status', 'total_tasks', 'completed_tasks', 'progress_percentage')
        }),
        ('Assignment', {
            'fields': ('hr_responsible', 'buddy')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(OnboardingTaskProgress)
class OnboardingTaskProgressAdmin(admin.ModelAdmin):
    list_display = ['title', 'onboarding', 'stage', 'assigned_to', 'due_date', 'status']
    list_filter = ['status', 'stage', 'is_mandatory']
    search_fields = ['title', 'onboarding__employee__employee_id']
    date_hierarchy = 'due_date'


@admin.register(OnboardingDocument)
class OnboardingDocumentAdmin(admin.ModelAdmin):
    list_display = ['onboarding', 'document_type', 'document_name', 'status', 'verified_by']
    list_filter = ['status', 'document_type', 'is_mandatory']
    search_fields = ['onboarding__employee__employee_id', 'document_name']
