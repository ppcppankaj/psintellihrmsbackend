"""
Leave Models - Leave Management
"""

import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import OrganizationEntity


def _assert_same_org(instance, related, field_name):
    """Ensure related object belongs to the same organization."""
    if not related:
        return
    related_org = getattr(related, 'organization_id', None)
    if related_org is None:
        return
    if instance.organization_id and related_org != instance.organization_id:
        raise ValidationError({field_name: 'Cross-organization reference blocked'})
    if not instance.organization_id:
        instance.organization = related.organization


def _assert_employee_org(instance, field_name='employee'):
    employee = getattr(instance, field_name, None)
    if not employee:
        return
    if instance.organization_id and employee.organization_id != instance.organization_id:
        raise ValidationError({field_name: 'Employee not in this organization'})
    if not instance.organization_id:
        instance.organization = employee.organization


def _assert_branch_org(instance, field_name='branch'):
    branch = getattr(instance, field_name, None)
    if not branch:
        return
    if instance.organization_id and branch.organization_id != instance.organization_id:
        raise ValidationError({field_name: 'Branch not in this organization'})
    if not instance.organization_id:
        instance.organization = branch.organization


COMP_OFF_LEAVE_CODE = 'COMP_OFF'


class LeaveType(OrganizationEntity):
    """Leave type definitions"""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    
    # Accrual settings
    annual_quota = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    accrual_type = models.CharField(max_length=20, choices=[
        ('yearly', 'Yearly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('none', 'No Accrual'),
    ], default='none')
    
    # Carry forward
    carry_forward_allowed = models.BooleanField(default=False)
    max_carry_forward = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    
    # Encashment
    encashment_allowed = models.BooleanField(default=False)
    max_encashment = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    
    # Settings
    is_paid = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)
    requires_attachment = models.BooleanField(default=False)
    min_days_notice = models.PositiveSmallIntegerField(default=0)
    max_consecutive_days = models.PositiveSmallIntegerField(null=True, blank=True)
    
    # Applicability
    applicable_gender = models.CharField(max_length=20, blank=True)  # '', 'male', 'female'
    applicable_after_months = models.PositiveSmallIntegerField(default=0)
    
    # Color for UI
    color = models.CharField(max_length=8, default='#1976D2')
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class LeavePolicy(OrganizationEntity):
    """Leave policy for groups of employees"""
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Settings
    sandwich_rule = models.BooleanField(default=False)  # Count weekends/holidays in between
    probation_leave_allowed = models.BooleanField(default=False)
    negative_balance_allowed = models.BooleanField(default=False)
    max_negative_balance = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    
    # Holiday handling
    count_holidays = models.BooleanField(default=False)
    count_weekends = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = 'Leave Policies'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class LeaveBalance(OrganizationEntity):
    """Employee leave balance per type"""
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='leave_balances'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.CASCADE,
        related_name='balances'
    )
    
    year = models.PositiveSmallIntegerField()
    
    # Balance
    opening_balance = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    accrued = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    taken = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    adjustment = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    carry_forward = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    encashed = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    
    class Meta:
        unique_together = ['employee', 'leave_type', 'year']
        ordering = ['-year', 'leave_type']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name} ({self.year})"
    
    @property
    def available_balance(self):
        return self.opening_balance + self.accrued + self.carry_forward + self.adjustment - self.taken - self.encashed

    def clean(self):
        super().clean()
        _assert_employee_org(self)
        _assert_same_org(self, self.leave_type, 'leave_type')


class LeaveRequest(OrganizationEntity):
    """Leave application"""
    
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REVOKED = 'revoked'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_REVOKED, 'Revoked'),
    ]
    
    DAY_FULL = 'full'
    DAY_FIRST_HALF = 'first_half'
    DAY_SECOND_HALF = 'second_half'
    
    DAY_CHOICES = [
        (DAY_FULL, 'Full Day'),
        (DAY_FIRST_HALF, 'First Half'),
        (DAY_SECOND_HALF, 'Second Half'),
    ]
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='leave_requests'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name='requests'
    )
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='leave_requests',
        help_text="Branch of the employee"
    )
    
    start_date = models.DateField()
    end_date = models.DateField()
    start_day_type = models.CharField(max_length=20, choices=DAY_CHOICES, default=DAY_FULL)
    end_day_type = models.CharField(max_length=20, choices=DAY_CHOICES, default=DAY_FULL)
    
    total_days = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.TextField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    # Contact during leave
    contact_number = models.CharField(max_length=15, blank=True)
    contact_address = models.TextField(blank=True)
    
    # Attachments
    attachment = models.FileField(upload_to='leave_attachments/', null=True, blank=True)
    
    # Approval workflow
    current_approver = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pending_leave_approvals'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name} ({self.start_date} to {self.end_date})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def clean(self):
        super().clean()
        _assert_employee_org(self)
        _assert_same_org(self, self.leave_type, 'leave_type')
        _assert_branch_org(self)
        _assert_employee_org(self, 'current_approver')

        if self.employee and not self.branch_id and hasattr(self.employee, 'branch'):
            branch = getattr(self.employee, 'branch', None)
            if branch:
                self.branch = branch
                _assert_branch_org(self)

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'End date cannot be earlier than start date'})

        if self.leave_type and self.leave_type.requires_attachment and not self.attachment:
            raise ValidationError({'attachment': 'Attachment is required for this leave type'})

        if self.start_date and self.leave_type and self.leave_type.min_days_notice:
            notice = (self.start_date - timezone.now().date()).days
            if notice < self.leave_type.min_days_notice:
                raise ValidationError({
                    'start_date': f'Minimum {self.leave_type.min_days_notice} days notice required'
                })

        if self.start_date and self.end_date and self.leave_type and self.leave_type.max_consecutive_days:
            consecutive = (self.end_date - self.start_date).days + 1
            if consecutive > self.leave_type.max_consecutive_days:
                raise ValidationError({
                    'end_date': f'Max consecutive days {self.leave_type.max_consecutive_days} exceeded'
                })

        if not self.start_day_type:
            self.start_day_type = self.DAY_FULL
        if not self.end_day_type:
            self.end_day_type = self.DAY_FULL

        if self.employee and self.leave_type and self.start_date and self.end_date:
            from .services import LeaveBalanceService, LeaveCalculationService

            policy = LeavePolicy.objects.filter(
                organization=self.organization,
                is_active=True
            ).order_by('-created_at').first()

            total_days, _ = LeaveCalculationService.calculate_leave_days(
                self.start_date,
                self.end_date,
                self.start_day_type,
                self.end_day_type,
                policy,
                self.employee
            )

            if total_days <= Decimal('0'):
                raise ValidationError({'total_days': 'No working days in selected period'})

            self.total_days = total_days

            if self.status in [self.STATUS_PENDING, self.STATUS_APPROVED]:
                has_balance, message = LeaveBalanceService.check_balance(
                    self.employee,
                    self.leave_type,
                    total_days,
                    self.start_date.year
                )

                if not has_balance:
                    raise ValidationError({'total_days': message})

    def save(self, *args, **kwargs):
        previous_status = getattr(self, '_original_status', None)
        self.full_clean()
        super().save(*args, **kwargs)
        self._sync_leave_balance(previous_status)
        self._original_status = self.status

    def _sync_leave_balance(self, previous_status):
        if not self.employee_id or not self.leave_type_id or not self.total_days:
            return
        if previous_status == self.status:
            return

        from .services import LeaveBalanceService

        if self.status == self.STATUS_APPROVED and previous_status != self.STATUS_APPROVED:
            LeaveBalanceService.deduct_balance(
                self.employee,
                self.leave_type,
                self.total_days,
                self.start_date.year
            )
        elif previous_status == self.STATUS_APPROVED and self.status in [
            self.STATUS_CANCELLED,
            self.STATUS_REVOKED,
        ]:
            LeaveBalanceService.restore_balance(
                self.employee,
                self.leave_type,
                self.total_days,
                self.start_date.year
            )


class LeaveApproval(OrganizationEntity):
    """Leave approval history"""
    
    leave_request = models.ForeignKey(
        LeaveRequest,
        on_delete=models.CASCADE,
        related_name='approvals'
    )
    approver = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        related_name='leave_approvals'
    )
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='leave_approvals',
        help_text="Branch where approval occurred"
    )
    
    level = models.PositiveSmallIntegerField(default=1)
    action = models.CharField(max_length=20, choices=[
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('forwarded', 'Forwarded'),
    ])
    comments = models.TextField(blank=True)
    
    class Meta:
        ordering = ['level', 'created_at']
    
    def __str__(self):
        return f"{self.leave_request} - Level {self.level} - {self.action}"

    def clean(self):
        super().clean()
        _assert_same_org(self, self.leave_request, 'leave_request')
        _assert_employee_org(self, 'approver')
        _assert_branch_org(self)
        if not self.branch_id and self.approver and hasattr(self.approver, 'branch'):
            branch = getattr(self.approver, 'branch', None)
            if branch:
                self.branch = branch
                _assert_branch_org(self)


class Holiday(OrganizationEntity):
    """Holiday calendar"""
    
    name = models.CharField(max_length=100)
    date = models.DateField()
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='holidays',
        help_text="Branch-specific holiday (null = organization-wide)"
    )
    
    is_optional = models.BooleanField(default=False)
    is_restricted = models.BooleanField(default=False)  # Restricted/floating holiday
    
    # Location-specific
    locations = models.ManyToManyField(
        'employees.Location',
        blank=True,
        related_name='holidays'
    )
    
    class Meta:
        ordering = ['date']
    
    def __str__(self):
        return f"{self.name} ({self.date})"

    def clean(self):
        super().clean()
        _assert_branch_org(self)


class LeaveEncashment(OrganizationEntity):
    """
    Leave encashment request.
    Allows employees to encash unused leaves for monetary compensation.
    """
    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_PROCESSED = 'processed'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='leave_encashments'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name='encashments'
    )
    
    # Encashment details
    year = models.PositiveSmallIntegerField()
    days_requested = models.DecimalField(max_digits=5, decimal_places=1)
    days_approved = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    
    # Calculation
    per_day_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    # Approval
    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_encashments'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Payment
    paid_in_payroll = models.ForeignKey(
        'payroll.PayrollRun',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='leave_encashments'
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.code} - {self.days_requested} days"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def clean(self):
        super().clean()
        _assert_employee_org(self)
        _assert_same_org(self, self.leave_type, 'leave_type')
        _assert_employee_org(self, 'approved_by')
        _assert_same_org(self, self.paid_in_payroll, 'paid_in_payroll')

        if self.days_requested and self.days_approved and self.days_approved > self.days_requested:
            raise ValidationError({'days_approved': 'Cannot exceed requested days'})

        if self.status == self.STATUS_APPROVED:
            if not self.leave_type or not self.leave_type.encashment_allowed:
                raise ValidationError({'leave_type': 'Encashment not allowed for this leave type'})
            if not self.days_approved:
                self.days_approved = self.days_requested
            if not self.per_day_amount:
                raise ValidationError({'per_day_amount': 'Per day amount required to approve'})

        if self.status == self.STATUS_PROCESSED and not self.paid_in_payroll:
            raise ValidationError({'paid_in_payroll': 'Processed encashments must link to a payroll run'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.days_approved and self.per_day_amount:
            self.total_amount = self.per_day_amount * self.days_approved
        super().save(*args, **kwargs)


class CompensatoryLeave(OrganizationEntity):
    """
    Compensatory off for working on holidays/weekends.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_USED = 'used'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_USED, 'Used'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    WORK_TYPE_HOLIDAY = 'holiday'
    WORK_TYPE_WEEKEND = 'weekend'
    WORK_TYPE_OVERTIME = 'overtime'
    
    WORK_TYPE_CHOICES = [
        (WORK_TYPE_HOLIDAY, 'Holiday Working'),
        (WORK_TYPE_WEEKEND, 'Weekend Working'),
        (WORK_TYPE_OVERTIME, 'Overtime (Extra Hours)'),
    ]
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='compensatory_leaves'
    )
    
    # Work details
    work_date = models.DateField()
    work_type = models.CharField(max_length=20, choices=WORK_TYPE_CHOICES)
    reason = models.TextField(help_text="Reason for working on off-day")
    
    # Hours worked (for overtime-based)
    hours_worked = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    
    # Comp-off credit
    days_credited = models.DecimalField(
        max_digits=3, decimal_places=1,
        default=1,
        help_text="Days to credit (0.5 for half day, 1 for full day)"
    )
    
    # Validity
    expiry_date = models.DateField(null=True, blank=True, help_text="Date by which comp-off must be used")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    # Approval
    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_comp_offs'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Usage tracking
    used_in_leave_request = models.ForeignKey(
        LeaveRequest,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='compensatory_leaves_used'
    )
    
    class Meta:
        ordering = ['-work_date']
    
    def __str__(self):
        return f"{self.employee.employee_id} - Comp-off for {self.work_date}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def clean(self):
        super().clean()
        _assert_employee_org(self)
        _assert_employee_org(self, 'approved_by')
        _assert_same_org(self, self.used_in_leave_request, 'used_in_leave_request')

        if self.used_in_leave_request and self.status != self.STATUS_USED:
            raise ValidationError({
                'used_in_leave_request': 'Usage can only be recorded when status is set to used'
            })

        if self.expiry_date and self.expiry_date < timezone.now().date() and self.status not in [
            self.STATUS_USED,
            self.STATUS_CANCELLED,
            self.STATUS_EXPIRED,
        ]:
            self.status = self.STATUS_EXPIRED

    def save(self, *args, **kwargs):
        previous_status = getattr(self, '_original_status', None)
        if self.expiry_date and self.expiry_date < timezone.now().date() and self.status not in [
            self.STATUS_USED,
            self.STATUS_CANCELLED,
            self.STATUS_EXPIRED,
        ]:
            self.status = self.STATUS_EXPIRED
        self.full_clean()
        super().save(*args, **kwargs)
        self._handle_status_change(previous_status)
        self._original_status = self.status

    def _handle_status_change(self, previous_status):
        if self.status == self.STATUS_APPROVED and previous_status != self.STATUS_APPROVED:
            from .services import LeaveBalanceService

            LeaveBalanceService.credit_comp_off_balance(
                employee=self.employee,
                days=self.days_credited,
                organization=self.organization,
            )


class HolidayCalendar(OrganizationEntity):
    """
    Named holiday calendar for organizing holidays by region/year.
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    country = models.CharField(max_length=50, default='India')
    year = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)
    
    is_default = models.BooleanField(default=False)
    
    # Regional associations
    locations = models.ManyToManyField(
        'employees.Location',
        blank=True,
        related_name='holiday_calendars'
    )
    
    class Meta:
        ordering = ['-year', 'name']
        unique_together = ['code', 'year']
    
    def __str__(self):
        return f"{self.name} ({self.year})"

    def clean(self):
        super().clean()
        if not self.organization_id:
            raise ValidationError({'organization': 'Organization is required for holiday calendars'})


class HolidayCalendarEntry(OrganizationEntity):
    """
    Individual holiday entries in a calendar.
    """
    calendar = models.ForeignKey(
        HolidayCalendar,
        on_delete=models.CASCADE,
        related_name='entries'
    )
    
    name = models.CharField(max_length=100)
    date = models.DateField()
    day_of_week = models.CharField(max_length=10, blank=True)
    
    is_optional = models.BooleanField(default=False)
    is_restricted = models.BooleanField(default=False, help_text="Restricted/floating holiday")
    
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['date']
        unique_together = ['calendar', 'date']
    
    def __str__(self):
        return f"{self.name} - {self.date}"
    
    def save(self, *args, **kwargs):
        self.full_clean()
        if self.date:
            self.day_of_week = self.date.strftime('%A')
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        _assert_same_org(self, self.calendar, 'calendar')

