"""Workflow Models - Multi-level Approval Workflow Engine"""
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import OrganizationEntity


WORKFLOW_ACTION_CHOICES = [
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('forwarded', 'Forwarded'),
    ('delegated', 'Delegated'),
    ('escalated', 'Escalated'),
    ('started', 'Started'),
    ('auto_approved', 'Auto Approved'),
    ('auto_rejected', 'Auto Rejected'),
]


class WorkflowDefinition(OrganizationEntity):
    """Workflow definition/template"""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    entity_type = models.CharField(max_length=50)  # leave_request, expense_claim, etc.
    
    # Workflow configuration as JSON
    steps = models.JSONField(default=list)
    conditions = models.JSONField(default=dict, blank=True)
    
    # SLA
    sla_hours = models.PositiveIntegerField(null=True, blank=True)
    auto_approve_on_sla = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        super().save(*args, **kwargs)


class WorkflowStep(OrganizationEntity):
    """Step in a workflow"""
    workflow = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE, related_name='workflow_steps')
    
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    
    approver_type = models.CharField(max_length=30, choices=[
        ('reporting_manager', 'Reporting Manager'),
        ('hr_manager', 'HR Manager'),
        ('department_head', 'Department Head'),
        ('role', 'Specific Role'),
        ('user', 'Specific User'),
    ])
    approver_role = models.ForeignKey('abac.Role', on_delete=models.SET_NULL, null=True, blank=True)
    approver_user = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, blank=True)
    
    is_optional = models.BooleanField(default=False)
    can_delegate = models.BooleanField(default=True)
    
    sla_hours = models.PositiveIntegerField(null=True, blank=True)
    escalate_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='escalations')
    
    class Meta:
        ordering = ['workflow', 'order']
        unique_together = ['workflow', 'order']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.workflow.name} - Step {self.order}: {self.name}"

    def clean(self):
        if self.workflow_id:
            workflow_org_id = self.workflow.organization_id
            if self.organization_id and workflow_org_id != self.organization_id:
                raise ValidationError("Workflow step organization must match its workflow organization.")

        if self.approver_user_id and self.organization_id:
            if self.approver_user.organization_id != self.organization_id:
                raise ValidationError("Approver user must belong to the same organization as the workflow step.")

        if self.escalate_to_id and self.organization_id:
            if self.escalate_to.organization_id != self.organization_id:
                raise ValidationError("Escalation step must belong to the same organization.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.workflow_id:
            self.organization = self.workflow.organization
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)


class WorkflowInstance(OrganizationEntity):
    """Instance of a workflow for a specific entity"""
    workflow = models.ForeignKey(WorkflowDefinition, on_delete=models.SET_NULL, null=True, related_name='instances')
    
    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField()
    
    current_step = models.PositiveSmallIntegerField(default=1)
    
    status = models.CharField(max_length=20, choices=[
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('escalated', 'Escalated'),
    ], default='in_progress')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    current_approver = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} - {self.status}"

    def clean(self):
        if self.workflow_id and self.organization_id:
            if self.workflow.organization_id != self.organization_id:
                raise ValidationError("Workflow instance organization must match workflow organization.")

        if self.current_approver_id and self.organization_id:
            if self.current_approver.organization_id != self.organization_id:
                raise ValidationError("Workflow approver must belong to the same organization as the instance.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.workflow_id:
            self.organization = self.workflow.organization
        if not self.organization_id and self.current_approver_id:
            self.organization = self.current_approver.organization
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)


class WorkflowAction(OrganizationEntity):
    """Action taken in a workflow instance"""
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name='actions')
    step = models.PositiveSmallIntegerField()
    
    actor = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True)
    
    action = models.CharField(max_length=20, choices=WORKFLOW_ACTION_CHOICES)
    
    comments = models.TextField(blank=True)
    
    class Meta:
        ordering = ['instance', 'step', 'created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.instance} - Step {self.step}: {self.action}"

    def clean(self):
        if self.instance_id:
            instance_org_id = self.instance.organization_id
            if self.organization_id and instance_org_id != self.organization_id:
                raise ValidationError("Workflow action organization must match workflow instance organization.")

        if self.actor_id and self.organization_id:
            if self.actor.organization_id != self.organization_id:
                raise ValidationError("Workflow action actor must belong to the same organization.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.instance_id:
            self.organization = self.instance.organization
        if not self.organization_id and self.actor_id:
            self.organization = self.actor.organization
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)
