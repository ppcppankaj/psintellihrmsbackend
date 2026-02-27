"""
Performance Models - OKRs, KPIs, Reviews
"""

from django.db import models
from apps.core.models import OrganizationEntity


class PerformanceCycle(OrganizationEntity):
    """Performance review cycle"""
    
    name = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Phases
    goal_setting_start = models.DateField(null=True, blank=True)
    goal_setting_end = models.DateField(null=True, blank=True)
    review_start = models.DateField(null=True, blank=True)
    review_end = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('review', 'Review Phase'),
        ('completed', 'Completed'),
    ], default='draft')
    
    class Meta:
        ordering = ['-year', '-start_date']
    
    def __str__(self):
        return self.name


class OKRObjective(OrganizationEntity):
    """OKR Objective"""
    
    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.CASCADE, related_name='objectives')
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='okr_objectives')
    
    # Parent-child goal linking for cascading goals
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_objectives'
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    weight = models.PositiveSmallIntegerField(default=100)
    
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft')
    
    progress = models.PositiveSmallIntegerField(default=0)  # 0-100
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    def get_descendants(self):
        """Get all child objectives recursively"""
        descendants = list(self.child_objectives.all())
        for child in self.child_objectives.all():
            descendants.extend(child.get_descendants())
        return descendants


class KeyResult(OrganizationEntity):
    """Key Result for OKR"""
    
    objective = models.ForeignKey(OKRObjective, on_delete=models.CASCADE, related_name='key_results')
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    metric_type = models.CharField(max_length=20, choices=[
        ('number', 'Number'),
        ('percentage', 'Percentage'),
        ('currency', 'Currency'),
        ('boolean', 'Yes/No'),
    ], default='number')
    
    target_value = models.DecimalField(max_digits=12, decimal_places=2)
    current_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    weight = models.PositiveSmallIntegerField(default=100)
    progress = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        ordering = ['objective', 'created_at']
    
    def __str__(self):
        return self.title


class PerformanceReview(OrganizationEntity):
    """Performance review"""
    
    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.CASCADE, related_name='reviews')
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE, related_name='performance_reviews')
    
    self_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    self_comments = models.TextField(blank=True)
    
    manager_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    manager_comments = models.TextField(blank=True)
    
    final_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('self_review', 'Self Review'),
        ('manager_review', 'Manager Review'),
        ('completed', 'Completed'),
    ], default='pending')
    
    class Meta:
        unique_together = ['cycle', 'employee']
        ordering = ['-cycle__year']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.cycle.name}"


class ReviewFeedback(OrganizationEntity):
    """360-degree feedback"""
    
    review = models.ForeignKey(PerformanceReview, on_delete=models.CASCADE, related_name='feedbacks')
    reviewer = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, related_name='given_feedbacks')
    
    relationship = models.CharField(max_length=20, choices=[
        ('self', 'Self'),
        ('manager', 'Manager'),
        ('peer', 'Peer'),
        ('reportee', 'Reportee'),
        ('external', 'External'),
    ])
    
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    feedback = models.TextField(blank=True)
    
    is_anonymous = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['relationship', 'created_at']
    
    def __str__(self):
        return f"Feedback for {self.review.employee.employee_id}"


class KeyResultArea(OrganizationEntity):
    """
    Key Result Area (KRA) definitions.
    Can be linked to designations for role-specific KRAs.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    
    # Optional designation linkage
    designation = models.ForeignKey(
        'employees.Designation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kras'
    )
    department = models.ForeignKey(
        'employees.Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kras'
    )
    
    # Weightage
    default_weightage = models.PositiveSmallIntegerField(
        default=100,
        help_text="Default weightage for this KRA (sum should be 100)"
    )
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class EmployeeKRA(OrganizationEntity):
    """
    Employee-specific KRA assignments.
    """
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='kras'
    )
    cycle = models.ForeignKey(
        PerformanceCycle,
        on_delete=models.CASCADE,
        related_name='employee_kras'
    )
    kra = models.ForeignKey(
        KeyResultArea,
        on_delete=models.CASCADE,
        related_name='employee_assignments'
    )
    
    # Custom weightage for this employee
    weightage = models.PositiveSmallIntegerField(default=100)
    
    # Target and achievement
    target = models.TextField(blank=True, help_text="Specific target for this KRA")
    achievement = models.TextField(blank=True)
    
    # Rating
    self_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    manager_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    final_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    
    comments = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['employee', 'cycle', 'kra']
        ordering = ['-weightage']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.kra.name}"


class KPI(OrganizationEntity):
    """
    Key Performance Indicator tracking.
    """
    METRIC_NUMBER = 'number'
    METRIC_PERCENTAGE = 'percentage'
    METRIC_CURRENCY = 'currency'
    METRIC_BOOLEAN = 'boolean'
    METRIC_RATING = 'rating'
    
    METRIC_CHOICES = [
        (METRIC_NUMBER, 'Number'),
        (METRIC_PERCENTAGE, 'Percentage'),
        (METRIC_CURRENCY, 'Currency'),
        (METRIC_BOOLEAN, 'Yes/No'),
        (METRIC_RATING, 'Rating (1-5)'),
    ]
    
    FREQUENCY_DAILY = 'daily'
    FREQUENCY_WEEKLY = 'weekly'
    FREQUENCY_MONTHLY = 'monthly'
    FREQUENCY_QUARTERLY = 'quarterly'
    FREQUENCY_YEARLY = 'yearly'
    
    FREQUENCY_CHOICES = [
        (FREQUENCY_DAILY, 'Daily'),
        (FREQUENCY_WEEKLY, 'Weekly'),
        (FREQUENCY_MONTHLY, 'Monthly'),
        (FREQUENCY_QUARTERLY, 'Quarterly'),
        (FREQUENCY_YEARLY, 'Yearly'),
    ]
    
    employee_kra = models.ForeignKey(
        EmployeeKRA,
        on_delete=models.CASCADE,
        related_name='kpis',
        null=True, blank=True
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='kpis'
    )
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Metric settings
    metric_type = models.CharField(max_length=20, choices=METRIC_CHOICES, default=METRIC_NUMBER)
    measurement_frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default=FREQUENCY_MONTHLY)
    
    # Target
    target_value = models.DecimalField(max_digits=12, decimal_places=2)
    threshold_value = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Minimum acceptable value"
    )
    stretch_value = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Stretch/exceptional target"
    )
    
    # Current value
    current_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Status
    is_achieved = models.BooleanField(default=False)
    achievement_percentage = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    
    class Meta:
        ordering = ['-period_start', 'name']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.name}"
    
    def calculate_achievement(self):
        """Calculate achievement percentage"""
        if self.target_value and self.target_value > 0:
            percentage = (self.current_value / self.target_value) * 100
            self.achievement_percentage = min(percentage, 150)  # Cap at 150%
            self.is_achieved = self.current_value >= self.target_value
            self.save(update_fields=['achievement_percentage', 'is_achieved'])


class Competency(OrganizationEntity):
    """
    Competency framework definitions.
    """
    LEVEL_BEGINNER = 1
    LEVEL_DEVELOPING = 2
    LEVEL_PROFICIENT = 3
    LEVEL_ADVANCED = 4
    LEVEL_EXPERT = 5
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    
    category = models.CharField(max_length=50, choices=[
        ('technical', 'Technical'),
        ('behavioral', 'Behavioral'),
        ('leadership', 'Leadership'),
        ('functional', 'Functional'),
    ], default='behavioral')
    
    # Level descriptions
    level_1_description = models.TextField(blank=True, help_text="Beginner level description")
    level_2_description = models.TextField(blank=True, help_text="Developing level description")
    level_3_description = models.TextField(blank=True, help_text="Proficient level description")
    level_4_description = models.TextField(blank=True, help_text="Advanced level description")
    level_5_description = models.TextField(blank=True, help_text="Expert level description")
    
    class Meta:
        ordering = ['category', 'name']
        verbose_name_plural = 'Competencies'
    
    def __str__(self):
        return self.name


class EmployeeCompetency(OrganizationEntity):
    """
    Employee competency assessment.
    """
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='competencies'
    )
    competency = models.ForeignKey(
        Competency,
        on_delete=models.CASCADE,
        related_name='employee_assessments'
    )
    cycle = models.ForeignKey(
        PerformanceCycle,
        on_delete=models.CASCADE,
        related_name='competency_assessments'
    )
    
    # Expected level (from designation)
    expected_level = models.PositiveSmallIntegerField(default=3)
    
    # Assessed levels
    self_assessed_level = models.PositiveSmallIntegerField(null=True, blank=True)
    manager_assessed_level = models.PositiveSmallIntegerField(null=True, blank=True)
    final_level = models.PositiveSmallIntegerField(null=True, blank=True)
    
    # Gap
    gap = models.SmallIntegerField(default=0, help_text="Difference between expected and final level")
    
    comments = models.TextField(blank=True)
    development_plan = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['employee', 'competency', 'cycle']
        ordering = ['competency__category', 'competency__name']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.competency.name}"
    
    def calculate_gap(self):
        if self.final_level and self.expected_level:
            self.gap = self.expected_level - self.final_level
            self.save(update_fields=['gap'])


class TrainingRecommendation(OrganizationEntity):
    """
    Automatic training suggestions based on competency gaps.
    """
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='training_recommendations'
    )
    competency = models.ForeignKey(
        Competency,
        on_delete=models.CASCADE,
        related_name='recommendations'
    )
    cycle = models.ForeignKey(
        PerformanceCycle,
        on_delete=models.CASCADE,
        related_name='recommendations'
    )
    
    suggested_training = models.CharField(max_length=255)
    priority = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], default='medium')
    
    is_completed = models.BooleanField(default=False)
    completion_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-priority', 'competency__name']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.suggested_training}"

