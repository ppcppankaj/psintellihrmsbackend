"""Reports Models"""
from django.db import models
from django.conf import settings
from apps.core.models import OrganizationEntity

class ReportTemplate(OrganizationEntity):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=30)
    query_config = models.JSONField(default=dict)
    columns = models.JSONField(default=list)
    filters = models.JSONField(default=list)
    
    def __str__(self):
        return self.name

class ScheduledReport(OrganizationEntity):
    template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE)
    schedule = models.CharField(max_length=50)  # cron expression
    recipients = models.JSONField(default=list)
    format = models.CharField(max_length=10, choices=[('pdf', 'PDF'), ('excel', 'Excel'), ('csv', 'CSV')])
    last_run = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.template.name} - {self.schedule}"

class GeneratedReport(OrganizationEntity):
    template = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL, null=True)
    generated_by = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True)
    filters_applied = models.JSONField(default=dict)
    file = models.FileField(upload_to='reports/')
    
    def __str__(self):
        return f"{self.template.name if self.template else 'Report'} - {self.created_at}"


class ReportExecution(OrganizationEntity):
    """Report execution record for async/sync runs"""
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    FORMAT_CSV = 'csv'
    FORMAT_XLSX = 'xlsx'
    FORMAT_PDF = 'pdf'

    FORMAT_CHOICES = [
        (FORMAT_CSV, 'CSV'),
        (FORMAT_XLSX, 'Excel'),
        (FORMAT_PDF, 'PDF'),
    ]

    template = models.ForeignKey(
        ReportTemplate,
        on_delete=models.SET_NULL,
        null=True,
        related_name='executions'
    )
    template_code = models.CharField(max_length=50, blank=True)
    template_name = models.CharField(max_length=100, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='report_executions'
    )
    filters = models.JSONField(default=dict, blank=True)
    parameters = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    output_format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default=FORMAT_CSV)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.PositiveIntegerField(null=True, blank=True)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    columns = models.JSONField(default=list, blank=True)

    file = models.FileField(upload_to='reports/executions/', null=True, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status', 'created_at'], name='rpt_exec_org_status_idx'),
            models.Index(fields=['requested_by', 'status', 'created_at'], name='rpt_exec_user_status_idx'),
            models.Index(fields=['template', 'status', 'created_at'], name='rpt_exec_tpl_status_idx'),
        ]

    def __str__(self):
        return f"Execution {self.id} - {self.status}"
