"""Compliance Models"""
from django.db import models
from apps.core.models import OrganizationEntity

class DataRetentionPolicy(OrganizationEntity):
    name = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50)
    retention_days = models.PositiveIntegerField()
    action = models.CharField(max_length=20, choices=[('archive', 'Archive'), ('delete', 'Delete'), ('anonymize', 'Anonymize')])
    date_field = models.CharField(max_length=50, default='created_at')
    filter_criteria = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.name} - {self.retention_days} days"

class ConsentRecord(OrganizationEntity):
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='consents')
    consent_type = models.CharField(max_length=50)
    granted = models.BooleanField(default=False)
    granted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.consent_type}"

class LegalHold(OrganizationEntity):
    name = models.CharField(max_length=100)
    description = models.TextField()
    employees = models.ManyToManyField('employees.Employee', related_name='legal_holds')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return self.name


class DataSubjectRequest(OrganizationEntity):
    """Data Subject Access Request (DSAR)"""
    REQUEST_ACCESS = 'access'
    REQUEST_DELETE = 'delete'
    REQUEST_RECTIFY = 'rectify'
    REQUEST_RESTRICT = 'restrict'

    REQUEST_CHOICES = [
        (REQUEST_ACCESS, 'Access'),
        (REQUEST_DELETE, 'Delete'),
        (REQUEST_RECTIFY, 'Rectify'),
        (REQUEST_RESTRICT, 'Restrict Processing'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_FULFILLED = 'fulfilled'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_FULFILLED, 'Fulfilled'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    request_type = models.CharField(max_length=20, choices=REQUEST_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='dsar_requests'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dsar_requests'
    )
    details = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    processed_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dsar_processed'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    response_file = models.FileField(upload_to='compliance/dsar/', null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.request_type} - {self.status}"


class AuditExportRequest(OrganizationEntity):
    """Audit log export requests"""
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

    requested_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_exports'
    )
    filters = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    file = models.FileField(upload_to='compliance/audit_exports/', null=True, blank=True)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Audit Export - {self.status}"


class RetentionExecution(OrganizationEntity):
    """Retention enforcement execution log"""
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

    policy = models.ForeignKey(DataRetentionPolicy, on_delete=models.CASCADE, related_name='executions')
    requested_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retention_executions'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    dry_run = models.BooleanField(default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    affected_count = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Retention Execution - {self.policy.name}"
