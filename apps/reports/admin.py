"""Reports Admin"""
from django.contrib import admin
from .models import ReportTemplate, ScheduledReport, GeneratedReport, ReportExecution

@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'report_type', 'is_active']
    list_filter = ['report_type', 'is_active']
    search_fields = ['name', 'code']

@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ['template', 'schedule', 'format', 'last_run', 'is_active']
    list_filter = ['format', 'is_active']

@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = ['template', 'generated_by', 'created_at']
    raw_id_fields = ['template', 'generated_by']


@admin.register(ReportExecution)
class ReportExecutionAdmin(admin.ModelAdmin):
    list_display = ['template_name', 'output_format', 'status', 'requested_by', 'created_at']
    list_filter = ['status', 'output_format']
    search_fields = ['template_name', 'template_code', 'requested_by__email']
