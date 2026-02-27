"""Recruitment Models - ATS with AI Resume Parsing"""
from django.db import models
from apps.core.models import OrganizationEntity


class JobPosting(OrganizationEntity):
    """Job posting"""
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    department = models.ForeignKey('employees.Department', on_delete=models.SET_NULL, null=True, related_name='job_postings')
    location = models.ForeignKey('employees.Location', on_delete=models.SET_NULL, null=True, related_name='job_postings')
    designation = models.ForeignKey('employees.Designation', on_delete=models.SET_NULL, null=True, related_name='job_postings')
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='job_postings',
        help_text="Branch this job posting is for"
    )
    
    description = models.TextField()
    requirements = models.TextField(blank=True)
    responsibilities = models.TextField(blank=True)
    
    employment_type = models.CharField(max_length=20, choices=[('full_time', 'Full Time'), ('part_time', 'Part Time'), ('contract', 'Contract'), ('intern', 'Intern')])
    experience_min = models.PositiveSmallIntegerField(default=0)
    experience_max = models.PositiveSmallIntegerField(null=True, blank=True)
    
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    positions = models.PositiveSmallIntegerField(default=1)
    
    status = models.CharField(max_length=20, choices=[('draft', 'Draft'), ('open', 'Open'), ('on_hold', 'On Hold'), ('closed', 'Closed')], default='draft')
    
    published_at = models.DateTimeField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    
    hiring_manager = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, related_name='hiring_jobs')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class Candidate(OrganizationEntity):
    """Candidate profile"""
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField()
    phone = models.CharField(max_length=15, blank=True)
    
    resume = models.FileField(upload_to='resumes/')
    parsed_data = models.JSONField(default=dict, blank=True)  # AI-parsed resume data
    
    source = models.CharField(max_length=50, choices=[('direct', 'Direct'), ('referral', 'Referral'), ('linkedin', 'LinkedIn'), ('naukri', 'Naukri'), ('indeed', 'Indeed'), ('other', 'Other')], default='direct')
    referred_by = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')
    
    total_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    current_company = models.CharField(max_length=200, blank=True)
    current_designation = models.CharField(max_length=200, blank=True)
    current_ctc = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_ctc = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_period = models.PositiveSmallIntegerField(null=True, blank=True)
    
    skills = models.JSONField(default=list, blank=True)
    education = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class JobApplication(OrganizationEntity):
    """Job application"""
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='applications')
    
    stage = models.CharField(max_length=30, choices=[
        ('new', 'New'), ('screening', 'Screening'), ('interview', 'Interview'),
        ('technical', 'Technical Round'), ('hr', 'HR Round'), ('offer', 'Offer'),
        ('hired', 'Hired'), ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn')
    ], default='new')
    
    ai_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_insights = models.JSONField(default=dict, blank=True)
    
    class Meta:
        unique_together = ['job', 'candidate']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.candidate} - {self.job.title}"


class Interview(OrganizationEntity):
    """Interview schedule"""
    application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='interviews')
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='interviews',
        help_text="Branch where interview takes place"
    )
    
    round_type = models.CharField(max_length=30, choices=[
        ('phone', 'Phone Screening'), ('technical', 'Technical'), ('hr', 'HR'),
        ('manager', 'Hiring Manager'), ('panel', 'Panel'), ('final', 'Final')
    ])
    
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    
    mode = models.CharField(max_length=20, choices=[('in_person', 'In Person'), ('video', 'Video Call'), ('phone', 'Phone')], default='video')
    meeting_link = models.URLField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    
    interviewers = models.ManyToManyField('employees.Employee', related_name='interviews')
    
    status = models.CharField(max_length=20, choices=[
        ('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('rescheduled', 'Rescheduled')
    ], default='scheduled')
    
    feedback = models.TextField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    recommendation = models.CharField(max_length=20, choices=[('hire', 'Hire'), ('reject', 'Reject'), ('hold', 'Hold'), ('next_round', 'Next Round')], blank=True)
    
    class Meta:
        ordering = ['scheduled_at']
    
    def __str__(self):
        return f"{self.application.candidate} - {self.round_type}"


class OfferLetter(OrganizationEntity):
    """Offer letter"""
    application = models.OneToOneField(JobApplication, on_delete=models.CASCADE, related_name='offer')
    
    offered_ctc = models.DecimalField(max_digits=12, decimal_places=2)
    designation = models.ForeignKey('employees.Designation', on_delete=models.SET_NULL, null=True)
    joining_date = models.DateField()
    
    offer_letter_file = models.FileField(upload_to='offers/', null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'), ('sent', 'Sent'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('expired', 'Expired')
    ], default='pending')
    
    valid_until = models.DateField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Offer - {self.application.candidate}"
