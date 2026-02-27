"""Training Models"""
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import OrganizationEntity


class TrainingCategory(OrganizationEntity):
    """Training categories (e.g., Compliance, Technical, Soft Skills)"""
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']
        unique_together = [('organization', 'code')]

    def __str__(self) -> str:
        return self.name


class TrainingProgram(OrganizationEntity):
    """Training programs/courses"""
    MODE_ONLINE = 'online'
    MODE_ONSITE = 'onsite'
    MODE_HYBRID = 'hybrid'

    MODE_CHOICES = [
        (MODE_ONLINE, 'Online'),
        (MODE_ONSITE, 'Onsite'),
        (MODE_HYBRID, 'Hybrid'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    category = models.ForeignKey(
        TrainingCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='programs'
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=60)
    description = models.TextField(blank=True)

    provider = models.CharField(max_length=200, blank=True)
    delivery_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_ONLINE)
    location = models.CharField(max_length=200, blank=True)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    enrollment_deadline = models.DateField(null=True, blank=True)
    duration_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)

    is_mandatory = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    prerequisites = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('organization', 'code')]

    def __str__(self) -> str:
        return self.name


class TrainingMaterial(OrganizationEntity):
    """Training materials for a program"""
    TYPE_DOCUMENT = 'document'
    TYPE_VIDEO = 'video'
    TYPE_LINK = 'link'
    TYPE_QUIZ = 'quiz'

    TYPE_CHOICES = [
        (TYPE_DOCUMENT, 'Document'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_LINK, 'Link'),
        (TYPE_QUIZ, 'Quiz'),
    ]

    program = models.ForeignKey(
        TrainingProgram,
        on_delete=models.CASCADE,
        related_name='materials'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    material_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DOCUMENT)
    file = models.FileField(upload_to='training/materials/', null=True, blank=True)
    url = models.URLField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_materials_uploaded'
    )

    class Meta:
        ordering = ['order', 'title']

    def clean(self):
        if not self.file and not self.url:
            raise ValidationError("Either file or url must be provided.")

    def __str__(self) -> str:
        return self.title


class TrainingEnrollment(OrganizationEntity):
    """Employee enrollment in a training program"""
    STATUS_ENROLLED = 'enrolled'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_ENROLLED, 'Enrolled'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    program = models.ForeignKey(
        TrainingProgram,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='training_enrollments'
    )
    assigned_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_assigned'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ENROLLED)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    certificate_file = models.FileField(upload_to='training/certificates/', null=True, blank=True)

    class Meta:
        ordering = ['-enrolled_at']
        unique_together = [('program', 'employee')]

    def __str__(self) -> str:
        return f"{self.program.name} - {self.employee.full_name}"


class TrainingCompletion(OrganizationEntity):
    """Completion record for training enrollment"""
    enrollment = models.OneToOneField(
        TrainingEnrollment,
        on_delete=models.CASCADE,
        related_name='completion'
    )
    completed_at = models.DateTimeField(auto_now_add=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    certificate_file = models.FileField(upload_to='training/certificates/', null=True, blank=True)

    class Meta:
        ordering = ['-completed_at']

    def __str__(self) -> str:
        return f"Completion - {self.enrollment}"
