"""
Onboarding Models - Employee Onboarding with Checklist Workflows

Inspired by Frappe HRMS onboarding features:
- Template-based onboarding checklists
- Task assignment by role
- Multi-stage onboarding process
- Pre-joining and post-joining tasks
"""

from django.db import models
from apps.core.models import OrganizationEntity


class OnboardingTemplate(OrganizationEntity):
    """
    Template for onboarding checklists.
    Can be linked to specific departments/designations or used as default.
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    
    # Optional targeting
    department = models.ForeignKey(
        'employees.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_templates'
    )
    designation = models.ForeignKey(
        'employees.Designation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_templates'
    )
    location = models.ForeignKey(
        'employees.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_templates'
    )
    
    # Timeline settings
    days_before_joining = models.PositiveSmallIntegerField(
        default=7,
        help_text="How many days before joining to start pre-boarding tasks"
    )
    days_to_complete = models.PositiveSmallIntegerField(
        default=30,
        help_text="Total days allowed to complete all onboarding tasks"
    )
    
    is_default = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class OnboardingTaskTemplate(OrganizationEntity):
    """
    Individual task definition within an onboarding template.
    """
    STAGE_PRE_JOINING = 'pre_joining'
    STAGE_DAY_ONE = 'day_one'
    STAGE_FIRST_WEEK = 'first_week'
    STAGE_FIRST_MONTH = 'first_month'
    STAGE_POST_ONBOARDING = 'post_onboarding'
    
    STAGE_CHOICES = [
        (STAGE_PRE_JOINING, 'Pre-Joining'),
        (STAGE_DAY_ONE, 'Day One'),
        (STAGE_FIRST_WEEK, 'First Week'),
        (STAGE_FIRST_MONTH, 'First Month'),
        (STAGE_POST_ONBOARDING, 'Post Onboarding'),
    ]
    
    ASSIGNEE_EMPLOYEE = 'employee'
    ASSIGNEE_HR = 'hr'
    ASSIGNEE_MANAGER = 'manager'
    ASSIGNEE_IT = 'it'
    ASSIGNEE_ADMIN = 'admin'
    ASSIGNEE_FINANCE = 'finance'
    
    ASSIGNEE_CHOICES = [
        (ASSIGNEE_EMPLOYEE, 'New Employee'),
        (ASSIGNEE_HR, 'HR Team'),
        (ASSIGNEE_MANAGER, 'Reporting Manager'),
        (ASSIGNEE_IT, 'IT Team'),
        (ASSIGNEE_ADMIN, 'Admin Team'),
        (ASSIGNEE_FINANCE, 'Finance Team'),
    ]
    
    template = models.ForeignKey(
        OnboardingTemplate,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default=STAGE_FIRST_WEEK)
    
    # Assignment
    assigned_to_type = models.CharField(max_length=20, choices=ASSIGNEE_CHOICES, default=ASSIGNEE_HR)
    assigned_to_role = models.ForeignKey(
        'abac.Role',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Specific role if assigned_to_type is not enough"
    )
    
    # Timeline
    due_days_offset = models.SmallIntegerField(
        default=0,
        help_text="Days from joining date. Negative for pre-joining tasks."
    )
    
    # Requirements
    is_mandatory = models.BooleanField(default=True)
    requires_attachment = models.BooleanField(default=False)
    requires_acknowledgement = models.BooleanField(default=False)
    
    # Dependencies
    depends_on = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dependent_tasks'
    )
    
    # Ordering
    order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        ordering = ['stage', 'order', 'due_days_offset']
    
    def __str__(self):
        return f"{self.template.name} - {self.title}"


class EmployeeOnboarding(OrganizationEntity):
    """
    Onboarding instance for a specific employee.
    Created when an employee is hired and assigned an onboarding template.
    """
    STATUS_NOT_STARTED = 'not_started'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, 'Not Started'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    employee = models.OneToOneField(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='onboarding'
    )
    template = models.ForeignKey(
        OnboardingTemplate,
        on_delete=models.SET_NULL,
        null=True,
        related_name='instances'
    )
    
    # Key dates
    joining_date = models.DateField()
    start_date = models.DateField(help_text="When onboarding process started")
    target_completion_date = models.DateField()
    actual_completion_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)
    
    # Progress tracking
    total_tasks = models.PositiveSmallIntegerField(default=0)
    completed_tasks = models.PositiveSmallIntegerField(default=0)
    progress_percentage = models.PositiveSmallIntegerField(default=0)
    
    # HR assignment
    hr_responsible = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_onboardings'
    )
    
    # Buddy system
    buddy = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='buddy_assignments'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-joining_date']
    
    def __str__(self):
        return f"Onboarding: {self.employee.employee_id}"
    
    def update_progress(self):
        """Update progress statistics based on completed tasks"""
        tasks = self.task_progress.all()
        self.total_tasks = tasks.count()
        self.completed_tasks = tasks.filter(status='completed').count()
        if self.total_tasks > 0:
            self.progress_percentage = int((self.completed_tasks / self.total_tasks) * 100)
        else:
            self.progress_percentage = 0
        self.save(update_fields=['total_tasks', 'completed_tasks', 'progress_percentage'])


class OnboardingTaskProgress(OrganizationEntity):
    """
    Progress tracking for individual onboarding tasks.
    Created from template tasks when onboarding is initiated.
    """
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_SKIPPED = 'skipped'
    STATUS_OVERDUE = 'overdue'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_SKIPPED, 'Skipped'),
        (STATUS_OVERDUE, 'Overdue'),
    ]
    
    onboarding = models.ForeignKey(
        EmployeeOnboarding,
        on_delete=models.CASCADE,
        related_name='task_progress'
    )
    task_template = models.ForeignKey(
        OnboardingTaskTemplate,
        on_delete=models.SET_NULL,
        null=True,
        related_name='progress_records'
    )
    
    # Task details (copied from template for historical record)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    stage = models.CharField(max_length=20)
    is_mandatory = models.BooleanField(default=True)
    
    # Assignment
    assigned_to = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_onboarding_tasks'
    )
    
    # Timeline
    due_date = models.DateField()
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_onboarding_tasks'
    )
    
    # Completion details
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to='onboarding/attachments/', null=True, blank=True)
    acknowledged = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['due_date', 'stage']
    
    def __str__(self):
        return f"{self.onboarding.employee.employee_id} - {self.title}"


class OnboardingDocument(OrganizationEntity):
    """
    Documents required/collected during onboarding.
    """
    DOCUMENT_ID_PROOF = 'id_proof'
    DOCUMENT_ADDRESS_PROOF = 'address_proof'
    DOCUMENT_EDUCATION = 'education'
    DOCUMENT_EXPERIENCE = 'experience'
    DOCUMENT_PAN = 'pan_card'
    DOCUMENT_AADHAAR = 'aadhaar'
    DOCUMENT_PASSPORT = 'passport'
    DOCUMENT_BANK = 'bank_details'
    DOCUMENT_PHOTO = 'photo'
    DOCUMENT_OTHER = 'other'
    
    DOCUMENT_CHOICES = [
        (DOCUMENT_ID_PROOF, 'ID Proof'),
        (DOCUMENT_ADDRESS_PROOF, 'Address Proof'),
        (DOCUMENT_EDUCATION, 'Education Certificate'),
        (DOCUMENT_EXPERIENCE, 'Experience Letter'),
        (DOCUMENT_PAN, 'PAN Card'),
        (DOCUMENT_AADHAAR, 'Aadhaar Card'),
        (DOCUMENT_PASSPORT, 'Passport'),
        (DOCUMENT_BANK, 'Bank Details'),
        (DOCUMENT_PHOTO, 'Passport Photo'),
        (DOCUMENT_OTHER, 'Other'),
    ]
    
    STATUS_PENDING = 'pending'
    STATUS_UPLOADED = 'uploaded'
    STATUS_VERIFIED = 'verified'
    STATUS_REJECTED = 'rejected'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    
    onboarding = models.ForeignKey(
        EmployeeOnboarding,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    document_type = models.CharField(max_length=20, choices=DOCUMENT_CHOICES)
    document_name = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to='onboarding/documents/')
    file_size = models.PositiveIntegerField(default=0)
    
    is_mandatory = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    verified_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_onboarding_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['document_type']
    
    def __str__(self):
        return f"{self.onboarding.employee.employee_id} - {self.get_document_type_display()}"

    def save(self, *args, **kwargs):
        if self.file and hasattr(self.file, 'size'):
            self.file_size = self.file.size
        super().save(*args, **kwargs)
