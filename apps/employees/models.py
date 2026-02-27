"""
Employee Models - Core HR Employee Management
"""

import uuid
from django.db import models
from django.conf import settings
from encrypted_model_fields.fields import EncryptedCharField
from apps.core.models import OrganizationEntity, MetadataModel
from django.core.exceptions import ValidationError


def _assert_same_org(instance, related_obj, field_name):
    """Helper to ensure related objects stay within the same organization."""
    if related_obj and hasattr(related_obj, "organization_id"):
        if instance.organization_id and related_obj.organization_id != instance.organization_id:
            raise ValidationError({field_name: "Must belong to the same organization"})


def _assert_employee_org(instance, employee_field):
    employee = getattr(instance, employee_field, None)
    if not employee:
        return
    if instance.organization_id and employee.organization_id != instance.organization_id:
        raise ValidationError({employee_field: "Employee must belong to the same organization"})


class Employee(OrganizationEntity, MetadataModel):
    """
    Employee master record.
    Links to User for authentication, contains HR-specific data.
    """
    
    # Employment Status
    STATUS_ACTIVE = 'active'
    STATUS_PROBATION = 'probation'
    STATUS_NOTICE = 'notice_period'
    STATUS_INACTIVE = 'inactive'
    STATUS_TERMINATED = 'terminated'
    
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PROBATION, 'Probation'),
        (STATUS_NOTICE, 'Notice Period'),
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_TERMINATED, 'Terminated'),
    ]
    
    # Employment Type
    TYPE_FULL_TIME = 'full_time'
    TYPE_PART_TIME = 'part_time'
    TYPE_CONTRACT = 'contract'
    TYPE_INTERN = 'intern'
    TYPE_CONSULTANT = 'consultant'
    
    TYPE_CHOICES = [
        (TYPE_FULL_TIME, 'Full Time'),
        (TYPE_PART_TIME, 'Part Time'),
        (TYPE_CONTRACT, 'Contract'),
        (TYPE_INTERN, 'Intern'),
        (TYPE_CONSULTANT, 'Consultant'),
    ]
    
    # Link to User
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employee'
    )
    
    # Employee ID
    employee_id = models.CharField(max_length=50, db_index=True)
    
    # Personal Information
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    marital_status = models.CharField(max_length=20, choices=[
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ], blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    nationality = models.CharField(max_length=50, default='Indian')
    
    # Organization
    department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees'
    )
    designation = models.ForeignKey(
        'Designation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees'
    )
    location = models.ForeignKey(
        'Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees'
    )
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='employees',
        help_text="Physical branch/location where employee works"
    )
    
    # Reporting
    reporting_manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='direct_reports'
    )
    hr_manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hr_reports'
    )
    
    # Employment Details
    employment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_FULL_TIME)
    employment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROBATION)
    date_of_joining = models.DateField()
    confirmation_date = models.DateField(null=True, blank=True)
    probation_end_date = models.DateField(null=True, blank=True)
    notice_period_days = models.PositiveSmallIntegerField(default=30)
    
    # Exit Details
    date_of_exit = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=100, blank=True)
    last_working_date = models.DateField(null=True, blank=True)
    
    # Work Details
    shift = models.ForeignKey(
        'attendance.Shift',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees'
    )
    work_mode = models.CharField(max_length=20, choices=[
        ('office', 'Office'),
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
    ], default='office')
    
    # Identity Documents (Encrypted)
    pan_number = EncryptedCharField(max_length=10, blank=True, db_index=True)
    aadhaar_number = EncryptedCharField(max_length=12, blank=True, db_index=True)
    passport_number = EncryptedCharField(max_length=20, blank=True)
    passport_expiry = models.DateField(null=True, blank=True)
    
    # PF & ESI (Encrypted)
    uan_number = EncryptedCharField(max_length=12, blank=True)
    pf_number = EncryptedCharField(max_length=22, blank=True)
    esi_number = EncryptedCharField(max_length=17, blank=True)
    
    # Profile
    bio = models.TextField(blank=True)
    linkedin_url = models.URLField(blank=True)
    
    class Meta:
        ordering = ['employee_id']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'employee_id'],
                name='uq_employee_org_employee_id'
            )
        ]
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['department', 'employment_status']),
            models.Index(fields=['reporting_manager']),
            models.Index(fields=['organization', 'employment_status', 'is_active'], name='emp_org_status_idx'),
            models.Index(fields=['organization', 'department'], name='emp_org_dept_idx'),
            models.Index(fields=['organization', 'designation'], name='emp_org_desig_idx'),
            models.Index(fields=['organization', 'location'], name='emp_org_loc_idx'),
            models.Index(fields=['organization', 'reporting_manager'], name='emp_org_mgr_idx'),
        ]
    
    def __str__(self):
        return f"{self.employee_id} - {self.user.full_name}"

    def clean(self):
        super().clean()

        org_id = self.organization_id

        required_fields = {
            'department': self.department_id,
            'designation': self.designation_id,
            'location': self.location_id,
            'branch': self.branch_id,
            'employment_type': self.employment_type,
            'date_of_joining': self.date_of_joining,
        }
        missing = [field for field, value in required_fields.items() if not value]
        if missing:
            raise ValidationError({field: "This field is required" for field in missing})

        if self.user_id and hasattr(self.user, "organization_id"):
            if self.user.organization_id != org_id:
                raise ValidationError("User must belong to same organization")

        if org_id:
            if self.branch_id and self.branch and self.branch.organization_id != org_id:
                raise ValidationError("Branch must belong to same organization")
            if self.department_id and self.department and self.department.organization_id != org_id:
                raise ValidationError("Department must belong to same organization")
            if self.designation_id and self.designation and self.designation.organization_id != org_id:
                raise ValidationError("Designation must belong to same organization")
            if self.location_id and self.location and self.location.organization_id != org_id:
                raise ValidationError("Location must belong to same organization")
            if self.reporting_manager_id and self.reporting_manager.organization_id != org_id:
                raise ValidationError({"reporting_manager": "Manager must belong to same organization"})
            if self.hr_manager_id and self.hr_manager.organization_id != org_id:
                raise ValidationError({"hr_manager": "HR Manager must belong to same organization"})
            if self.shift_id and self.shift.organization_id != org_id:
                raise ValidationError({"shift": "Shift must belong to same organization"})

    
    @property
    def full_name(self):
        return self.user.full_name
    
    @property
    def email(self):
        return self.user.email
    
    def get_team_members(self):
        """Get all direct reports"""
        return Employee.objects.filter(reporting_manager=self, is_active=True)
    
    def get_org_hierarchy(self):
        """Get reporting chain up to top"""
        hierarchy = []
        current = self.reporting_manager
        while current:
            hierarchy.append(current)
            current = current.reporting_manager
        return hierarchy


class Department(OrganizationEntity):
    """Department/Business Unit"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='departments',
        help_text="Branch this department belongs to (null = organization-wide)"
    )
    
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_departments'
    )
    
    head = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments'
    )
    
    cost_center = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='uq_department_org_code'
            )
        ]
        indexes = [
            models.Index(fields=['organization', 'name'], name='idx_department_org_name')
        ]

    
    def __str__(self):
        return self.name
    
    def get_all_employees(self):
        """Get all employees including sub-departments using a non-recursive flat query"""
        sub_dept_ids = self.sub_departments.all().values_list('id', flat=True)
        # For multi-level nesting, we should ideally use MPTT, but for a simple fix:
        from django.db.models import Q
        return Employee.objects.filter(
            Q(department=self) | Q(department_id__in=sub_dept_ids),
            is_active=True,
            is_deleted=False
        )

    def clean(self):
        if self.branch_id and self.branch.organization_id != self.organization_id:
            raise ValidationError({"branch": "Branch must belong to same organization"})
        if self.parent_id and self.parent.organization_id != self.organization_id:
            raise ValidationError({"parent": "Parent department must belong to same organization"})
        if self.head_id and self.head.organization_id != self.organization_id:
            raise ValidationError({"head": "Head must belong to same organization"})



class Designation(OrganizationEntity):
    """Job Title/Designation"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    
    # Level for hierarchy
    level = models.PositiveSmallIntegerField(default=1)
    
    # Band/Grade
    grade = models.CharField(max_length=20, blank=True)
    
    # Job family
    job_family = models.CharField(max_length=50, blank=True)
    
    # Salary range
    min_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='uq_designation_org_code'
            )
        ]

    
    def __str__(self):
        return f"{self.name} ({self.grade})"

    def clean(self):
        pass # No foreign keys to validate against organization


class Location(OrganizationEntity):
    """Work Location/Office"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20)
    
    # Geo location for attendance
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    geo_fence_radius = models.PositiveIntegerField(default=200)  # meters
    
    # Contact
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Timezone
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    
    # Status
    is_headquarters = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name}, {self.city}"

    def clean(self):
        pass # No foreign keys to validate against organization


class EmployeeAddress(OrganizationEntity):
    """Employee Address Records"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    
    address_type = models.CharField(max_length=20, choices=[
        ('permanent', 'Permanent'),
        ('current', 'Current'),
        ('temporary', 'Temporary'),
    ])
    
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20)
    
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = 'Employee Addresses'
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.address_type}"
    
    def clean(self):
        if self.employee.organization_id != self.organization_id:
            raise ValidationError("Employee must belong to same organization")


class EmployeeBankAccount(OrganizationEntity):
    """Employee Bank Account Details"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='bank_accounts'
    )
    
    account_holder_name = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100)
    branch_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=255)  # Stored Encrypted
    ifsc_code = models.CharField(max_length=11)
    
    account_type = models.CharField(max_length=20, choices=[
        ('savings', 'Savings'),
        ('current', 'Current'),
        ('salary', 'Salary'),
    ], default='savings')
    
    is_primary = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-is_primary']
    
    def clean(self):
        if self.employee.organization_id != self.organization_id:
            raise ValidationError("Employee must belong to same organization")    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.bank_name}"

    def save(self, *args, **kwargs):
        from apps.core.encryption import encrypt_value
        # Only encrypt if not already encrypted (naive check: Fernet tokens usually start with gAAAA)
        if self.account_number and not self.account_number.startswith('gAAAA'):
            self.account_number = encrypt_value(self.account_number)
        super().save(*args, **kwargs)

    @property
    def decrypted_account_number(self):
        from apps.core.encryption import decrypt_value
        return decrypt_value(self.account_number)


class EmergencyContact(OrganizationEntity):
    """Employee Emergency Contacts"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='emergency_contacts'
    )
    
    name = models.CharField(max_length=100)
    relationship = models.CharField(max_length=50)
    phone = models.CharField(max_length=15)
    alternate_phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-is_primary', 'name']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.name}"

    def clean(self):
        if self.employee.organization_id != self.organization_id:
            raise ValidationError("Employee must belong to same organization")


class EmployeeDependent(OrganizationEntity):
    """Employee Family/Dependents"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='dependents'
    )
    
    name = models.CharField(max_length=100)
    relationship = models.CharField(max_length=50, choices=[
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    ])
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    
    # Insurance coverage
    is_covered_in_insurance = models.BooleanField(default=False)
    
    # For children
    is_disabled = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['relationship', 'name']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.name} ({self.relationship})"

    def clean(self):
        if self.employee.organization_id != self.organization_id:
            raise ValidationError("Employee must belong to same organization")

class Skill(OrganizationEntity):
    """Skill definitions"""
    
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['category', 'name']
    
    def __str__(self):
        return self.name


class EmployeeSkill(OrganizationEntity):
    """Employee skill assignments"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='skills'
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name='employee_skills'
    )
    
    proficiency = models.CharField(max_length=20, choices=[
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ])
    
    years_of_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_skills'
    )
    
    class Meta:
        unique_together = ['employee', 'skill']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'skill'],
                name='uq_employee_skill'
            )
        ]
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.skill.name}"

    def clean(self):
        _assert_employee_org(self, 'employee')
        _assert_same_org(self, self.skill, 'skill')
        if self.verified_by_id:
            _assert_same_org(self, self.verified_by, 'verified_by')


class EmploymentHistory(OrganizationEntity):
    """Track employment changes (promotions, transfers, etc.)"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='employment_history'
    )
    
    change_type = models.CharField(max_length=30, choices=[
        ('joining', 'Joining'),
        ('confirmation', 'Confirmation'),
        ('promotion', 'Promotion'),
        ('transfer', 'Transfer'),
        ('redesignation', 'Redesignation'),
        ('department_change', 'Department Change'),
        ('salary_revision', 'Salary Revision'),
        ('resignation', 'Resignation'),
        ('termination', 'Termination'),
    ])
    
    effective_date = models.DateField()
    
    # Previous values
    previous_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    previous_designation = models.ForeignKey(
        Designation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    previous_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    previous_manager = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    
    # New values
    new_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    new_designation = models.ForeignKey(
        Designation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    new_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    new_manager = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    
    remarks = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-effective_date']
        verbose_name_plural = 'Employment Histories'
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.change_type} on {self.effective_date}"

    def clean(self):
        _assert_employee_org(self, 'employee')
        for field in [
            'previous_department', 'previous_designation', 'previous_location', 'previous_manager',
            'new_department', 'new_designation', 'new_location', 'new_manager'
        ]:
            related = getattr(self, field)
            if related:
                _assert_same_org(self, related, field)

class Document(OrganizationEntity):
    """Document vault for employees"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    document_type = models.CharField(max_length=50, choices=[
        ('resume', 'Resume'),
        ('offer_letter', 'Offer Letter'),
        ('appointment_letter', 'Appointment Letter'),
        ('id_proof', 'ID Proof'),
        ('address_proof', 'Address Proof'),
        ('education', 'Education Certificate'),
        ('experience', 'Experience Letter'),
        ('relieving', 'Relieving Letter'),
        ('payslip', 'Payslip'),
        ('form16', 'Form 16'),
        ('nda', 'NDA'),
        ('other', 'Other'),
    ])
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='documents/')
    file_size = models.PositiveIntegerField(default=0)
    file_type = models.CharField(max_length=50, blank=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Expiry
    expiry_date = models.DateField(null=True, blank=True)
    
    # Access control
    is_confidential = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.name}"

    def clean(self):
        _assert_employee_org(self, 'employee')
        if self.verified_by_id:
            _assert_same_org(self, self.verified_by, 'verified_by')


class Certification(OrganizationEntity):
    """Employee professional certifications"""
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='certifications'
    )
    
    name = models.CharField(max_length=255)
    issuing_organization = models.CharField(max_length=255)
    credential_id = models.CharField(max_length=100, blank=True)
    credential_url = models.URLField(blank=True)
    
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_certifications'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Attachment
    certificate_file = models.FileField(upload_to='certifications/', blank=True, null=True)
    
    class Meta:
        ordering = ['-issue_date']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.name}"

    def clean(self):
        _assert_employee_org(self, 'employee')
        if self.verified_by_id:
            _assert_same_org(self, self.verified_by, 'verified_by')

    @property
    def is_expired(self):
        if self.expiry_date:
            from django.utils import timezone
            return self.expiry_date < timezone.now().date()
        return False


class EmployeeTransfer(OrganizationEntity):
    """
    Employee transfer request.
    Tracks department/location/manager changes with approval workflow.
    """
    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    TRANSFER_DEPARTMENT = 'department'
    TRANSFER_LOCATION = 'location'
    TRANSFER_MANAGER = 'manager'
    TRANSFER_COMBINED = 'combined'
    
    TRANSFER_TYPE_CHOICES = [
        (TRANSFER_DEPARTMENT, 'Department Transfer'),
        (TRANSFER_LOCATION, 'Location Transfer'),
        (TRANSFER_MANAGER, 'Reporting Manager Change'),
        (TRANSFER_COMBINED, 'Combined Transfer'),
    ]
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='transfers'
    )
    
    transfer_type = models.CharField(max_length=20, choices=TRANSFER_TYPE_CHOICES)
    
    # Current/From values
    department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_from_department',
        db_index=True
    )
    designation = models.ForeignKey(
        'Designation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_from_designation',
        db_index=True
    )
    location = models.ForeignKey(
        'Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_from_location',
        db_index=True
    )
    to_department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='incoming_transfers'
    )
    to_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='incoming_transfers'
    )
    to_manager = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='incoming_team_transfers'
    )
    
    # Dates
    requested_date = models.DateField()
    effective_date = models.DateField()
    
    # Reason
    reason = models.TextField()
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    # Approval
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_transfers'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Initiated by
    initiated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='initiated_transfers'
    )
    
    class Meta:
        ordering = ['-requested_date']
    
    def clean(self):
        _assert_employee_org(self, 'employee')
        _assert_same_org(self, self.department, 'department')
        _assert_same_org(self, self.designation, 'designation')
        _assert_same_org(self, self.location, 'location')
        _assert_same_org(self, self.to_department, 'to_department')
        _assert_same_org(self, self.to_location, 'to_location')
        _assert_same_org(self, self.to_manager, 'to_manager')
        if self.approved_by_id:
            _assert_same_org(self, self.approved_by, 'approved_by')
        if self.initiated_by_id:
            _assert_same_org(self, self.initiated_by, 'initiated_by')

    def __str__(self):
        return f"{self.employee.employee_id} - {self.get_transfer_type_display()}"


class EmployeePromotion(OrganizationEntity):
    """
    Employee promotion request.
    Tracks designation/grade changes with salary revision.
    """
    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='promotions'
    )
    
    # Designation change
    from_designation = models.ForeignKey(
        Designation,
        on_delete=models.SET_NULL,
        null=True,
        related_name='promotions_from'
    )
    to_designation = models.ForeignKey(
        Designation,
        on_delete=models.SET_NULL,
        null=True,
        related_name='promotions_to'
    )
    
    # Salary revision
    current_ctc = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    new_ctc = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    increment_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Dates
    requested_date = models.DateField()
    effective_date = models.DateField()
    
    # Reason/Justification
    reason = models.TextField()
    achievements = models.TextField(blank=True, help_text="Key achievements justifying promotion")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    # Approval
    recommended_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='recommended_promotions'
    )
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_promotions'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-requested_date']
    
    def __str__(self):
        return f"{self.employee.employee_id} - Promotion to {self.to_designation}"

    def clean(self):
        _assert_employee_org(self, 'employee')
        _assert_same_org(self, self.from_designation, 'from_designation')
        _assert_same_org(self, self.to_designation, 'to_designation')
        if self.recommended_by_id:
            _assert_same_org(self, self.recommended_by, 'recommended_by')
        if self.approved_by_id:
            _assert_same_org(self, self.approved_by, 'approved_by')

class ResignationRequest(OrganizationEntity):
    """
    Employee resignation request with approval workflow.
    """
    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_WITHDRAWN = 'withdrawn'
    STATUS_COMPLETED = 'completed'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_WITHDRAWN, 'Withdrawn'),
        (STATUS_COMPLETED, 'Separation Completed'),
    ]
    
    REASON_BETTER_OPPORTUNITY = 'better_opportunity'
    REASON_PERSONAL = 'personal'
    REASON_RELOCATION = 'relocation'
    REASON_HEALTH = 'health'
    REASON_HIGHER_STUDIES = 'higher_studies'
    REASON_CAREER_CHANGE = 'career_change'
    REASON_COMPENSATION = 'compensation'
    REASON_WORK_CULTURE = 'work_culture'
    REASON_OTHER = 'other'
    
    REASON_CHOICES = [
        (REASON_BETTER_OPPORTUNITY, 'Better Opportunity'),
        (REASON_PERSONAL, 'Personal Reasons'),
        (REASON_RELOCATION, 'Relocation'),
        (REASON_HEALTH, 'Health Issues'),
        (REASON_HIGHER_STUDIES, 'Higher Studies'),
        (REASON_CAREER_CHANGE, 'Career Change'),
        (REASON_COMPENSATION, 'Compensation'),
        (REASON_WORK_CULTURE, 'Work Culture'),
        (REASON_OTHER, 'Other'),
    ]
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='resignations'
    )
    
    # Dates
    resignation_date = models.DateField()
    requested_last_working_date = models.DateField()
    approved_last_working_date = models.DateField(null=True, blank=True)
    
    # Notice period
    notice_period_days = models.PositiveSmallIntegerField()
    notice_period_waived = models.PositiveSmallIntegerField(default=0)
    shortfall_recovery = models.BooleanField(default=False, help_text="Recover salary for shortfall notice period")
    
    # Reason
    primary_reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    detailed_reason = models.TextField(blank=True)
    new_employer = models.CharField(max_length=200, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    # Approval
    accepted_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='accepted_resignations'
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Exit checklist completed
    exit_checklist_complete = models.BooleanField(default=False)
    fnf_processed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-resignation_date']
    
    def __str__(self):
        return f"{self.employee.employee_id} - Resignation ({self.resignation_date})"

    def clean(self):
        _assert_employee_org(self, 'employee')
        if self.accepted_by_id:
            _assert_same_org(self, self.accepted_by, 'accepted_by')

class ExitInterview(OrganizationEntity):
    """
    Exit interview questionnaire for separating employees.
    Collects feedback for improving retention.
    """
    resignation = models.OneToOneField(
        ResignationRequest,
        on_delete=models.CASCADE,
        related_name='exit_interview'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='exit_interviews'
    )
    
    # Interview details
    interview_date = models.DateField()
    interviewer = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='conducted_exit_interviews'
    )
    
    # Ratings (1-5 scale)
    job_satisfaction = models.PositiveSmallIntegerField(null=True, blank=True)
    work_life_balance = models.PositiveSmallIntegerField(null=True, blank=True)
    management_support = models.PositiveSmallIntegerField(null=True, blank=True)
    growth_opportunities = models.PositiveSmallIntegerField(null=True, blank=True)
    compensation_satisfaction = models.PositiveSmallIntegerField(null=True, blank=True)
    work_environment = models.PositiveSmallIntegerField(null=True, blank=True)
    team_collaboration = models.PositiveSmallIntegerField(null=True, blank=True)
    
    # Open-ended feedback
    reason_for_leaving = models.TextField()
    liked_most = models.TextField(blank=True, help_text="What did you like most about working here?")
    improvements_suggested = models.TextField(blank=True, help_text="What could we improve?")
    would_recommend = models.BooleanField(null=True, blank=True, help_text="Would you recommend this company?")
    would_return = models.BooleanField(null=True, blank=True, help_text="Would you consider returning?")
    
    # Additional structured feedback (JSON)
    additional_feedback = models.JSONField(default=dict, blank=True)
    
    # Status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Confidentiality
    is_confidential = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-interview_date']
    
    def __str__(self):
        return f"Exit Interview - {self.employee.employee_id}"
    
    @property
    def average_rating(self):
        ratings = [
            self.job_satisfaction, self.work_life_balance, self.management_support,
            self.growth_opportunities, self.compensation_satisfaction,
            self.work_environment, self.team_collaboration
        ]
        valid_ratings = [r for r in ratings if r is not None]
        if valid_ratings:
            return sum(valid_ratings) / len(valid_ratings)
        return None

    def clean(self):
        _assert_employee_org(self, 'employee')
        _assert_same_org(self, self.resignation, 'resignation')
        if self.interviewer_id:
            _assert_same_org(self, self.interviewer, 'interviewer')

class SeparationChecklist(OrganizationEntity):
    """
    Checklist items for employee separation process.
    """
    resignation = models.ForeignKey(
        ResignationRequest,
        on_delete=models.CASCADE,
        related_name='checklist_items'
    )
    
    task_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    assigned_to_department = models.CharField(max_length=50, choices=[
        ('hr', 'HR'),
        ('it', 'IT'),
        ('finance', 'Finance'),
        ('admin', 'Admin'),
        ('manager', 'Reporting Manager'),
        ('employee', 'Employee'),
    ])
    assigned_to = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='separation_tasks'
    )
    
    due_date = models.DateField(null=True, blank=True)
    
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='completed_separation_tasks'
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        ordering = ['order', 'task_name']
    
    def __str__(self):
        return f"{self.resignation.employee.employee_id} - {self.task_name}"

    def clean(self):
        if self.resignation.employee.organization_id != self.organization_id:
            raise ValidationError({"resignation": "Resignation must belong to same organization"})
        if self.assigned_to_id:
            _assert_same_org(self, self.assigned_to, 'assigned_to')
        if self.completed_by_id:
            _assert_same_org(self, self.completed_by, 'completed_by')
