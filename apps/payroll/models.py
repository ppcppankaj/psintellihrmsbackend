from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import OrganizationEntity
from django.db.models import Q


def _assert_same_org(instance, related_obj, field_name):
    if related_obj is None:
        return
    if instance.organization_id and hasattr(related_obj, "organization_id"):
        if related_obj.organization_id != instance.organization_id:
            raise ValidationError({field_name: "Must belong to the same organization."})


def _assert_employee_org(instance, field_name='employee'):
    employee = getattr(instance, field_name, None)
    if employee is None:
        return
    if instance.organization_id and employee.organization_id != instance.organization_id:
        raise ValidationError({field_name: "Employee must belong to the same organization."})



# =====================================================
# EMPLOYEE SALARY (Versioned, Auto Calculated)
# =====================================================

class EmployeeSalary(OrganizationEntity):
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='salary_structures'
    )

    effective_from = models.DateField(db_index=True, default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)

    # -------- Earnings --------
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hra = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    da = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    special_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    conveyance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    medical_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    lta = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    other_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    performance_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    variable_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    arrears = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # -------- Deductions --------
    pf_employee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    esi_employee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    professional_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tds = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # -------- Employer Contributions --------
    pf_employer = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    esi_employer = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gratuity = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # -------- Totals --------
    annual_ctc = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monthly_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['employee', 'effective_from']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['employee','organization'],
                condition=Q(is_active=True),
                name='uq_active_salary_per_employee'
        )
    ]

    def clean(self):
        super().clean()
        _assert_employee_org(self)

        end_date = self.effective_to or timezone.now().date()

        overlapping = EmployeeSalary.objects.filter(
            employee=self.employee,
            organization=self.organization,
            effective_from__lte=end_date
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=self.effective_from)
        ).exclude(pk=self.pk)


        if overlapping.exists():
            raise ValidationError(
                "Salary effective date range overlaps with an existing salary record."
            )

        if self.is_active:
            qs = EmployeeSalary.objects.filter(
                employee=self.employee,
                organization=self.organization,
                is_active=True
            ).exclude(pk=self.pk)

            if qs.exists():
                raise ValidationError(
                    "Only one active salary structure is allowed per employee."
                )

    def calculate_totals(self):
        earnings = [
            self.basic, self.hra, self.da, self.special_allowance,
            self.conveyance, self.medical_allowance, self.lta,
            self.other_allowances, self.performance_bonus,
            self.variable_pay, self.arrears
        ]

        deductions = [
            self.pf_employee, self.esi_employee,
            self.professional_tax, self.tds,
            self.other_deductions
        ]

        self.monthly_gross = sum(earnings, Decimal('0.00'))
        self.total_deductions = sum(deductions, Decimal('0.00'))
        self.net_salary = self.monthly_gross - self.total_deductions

        self.annual_ctc = (
            (self.monthly_gross * 12) +
            self.pf_employer +
            self.esi_employer +
            self.gratuity
        )

    def save(self, *args, **kwargs):
        self.calculate_totals()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - {self.annual_ctc}"
    

# =====================================================
# PAYROLL RUN (Locking + Approval Workflow)
# =====================================================

class PayrollRun(OrganizationEntity):
    STATUS_DRAFT = 'draft'
    STATUS_PROCESSING = 'processing'
    STATUS_PROCESSED = 'processed'
    STATUS_PENDING_APPROVAL = 'pending_approval'
    STATUS_APPROVED = 'approved'
    STATUS_LOCKED = 'locked'
    STATUS_PAID = 'paid'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_PENDING_APPROVAL, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_LOCKED, 'Locked'),
        (STATUS_PAID, 'Paid'),
    ]

    name = models.CharField(max_length=100)
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    branch = models.ForeignKey(
        'authentication.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='payroll_runs',
        help_text="Branch this payroll run is for (null = organization-wide)"
    )
    pay_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    total_employees = models.PositiveIntegerField(default=0)
    total_gross = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    processed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    processed_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payrolls'
    )

    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payrolls'
    )

    class Meta:
        ordering = ['-year', '-month']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'year', 'month', 'branch'],
                name='uq_payroll_org_month_branch'
            )
        ]
            

    def lock(self):
        if self.status != self.STATUS_APPROVED:
            raise ValidationError("Only approved payroll can be locked.")
        self.status = self.STATUS_LOCKED
        self.locked_at = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.name} ({self.month}/{self.year})"

    def clean(self):
        super().clean()
        if self.branch_id and hasattr(self.branch, 'organization_id'):
            if self.organization_id and self.branch.organization_id != self.organization_id:
                raise ValidationError({'branch': 'Branch must belong to the same organization.'})
        _assert_employee_org(self, 'processed_by')
        _assert_employee_org(self, 'approved_by')


# =====================================================
# PAYSLIP (Snapshot-Based, Immutable)
# =====================================================

class Payslip(OrganizationEntity):
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name='payslips'
    )

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='payslips'
    )

    salary_snapshot = models.JSONField(default=dict)
    attendance_snapshot = models.JSONField(default=dict)

    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    earnings_breakdown = models.JSONField(default=dict)
    deductions_breakdown = models.JSONField(default=dict)

    pdf_file = models.FileField(upload_to='payslips/', null=True, blank=True)

    class Meta:
        ordering = ['employee__employee_id']
        constraints = [
                models.UniqueConstraint(
                    fields=['organization', 'payroll_run', 'employee'],
                    name='uq_payslip_per_employee_per_run'
                )
        ]
        

    def clean(self):
        super().clean()
        if self.payroll_run.status == PayrollRun.STATUS_LOCKED:
            raise ValidationError("Cannot modify payslip after payroll is locked.")
        if self.organization_id and self.payroll_run.organization_id != self.organization_id:
            raise ValidationError({'payroll_run': 'Payroll run belongs to different organization.'})
        _assert_employee_org(self)


    def __str__(self):
        return f"{self.employee} - {self.payroll_run.month}/{self.payroll_run.year}"


# =====================================================
# PF CONTRIBUTION
# =====================================================

class PFContribution(OrganizationEntity):
    payslip = models.OneToOneField(
        Payslip,
        on_delete=models.CASCADE,
        related_name='pf_contribution'
    )

    uan = models.CharField(max_length=12)
    pf_number = models.CharField(max_length=22, blank=True)

    epf_employee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    epf_employer = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    eps = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    edli = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    admin_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    pf_wages = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.payslip.employee} - PF"

    def clean(self):
        super().clean()
        if self.organization_id and self.payslip.organization_id != self.organization_id:
            raise ValidationError({'payslip': 'Payslip belongs to different organization.'})


# =====================================================
# TAX DECLARATION (Computation Ready)
# =====================================================

class TaxDeclaration(OrganizationEntity):
    TAX_REGIME_OLD = 'old'
    TAX_REGIME_NEW = 'new'

    TAX_REGIME_CHOICES = [
        (TAX_REGIME_OLD, 'Old Regime'),
        (TAX_REGIME_NEW, 'New Regime'),
    ]

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='tax_declarations'
    )

    financial_year = models.CharField(max_length=9)  # 2024-2025

    tax_regime = models.CharField(
        max_length=10,
        choices=TAX_REGIME_CHOICES,
        default=TAX_REGIME_NEW
    )

    declarations = models.JSONField(default=dict)

    proofs_submitted = models.BooleanField(default=False)
    proofs_verified = models.BooleanField(default=False)

    verified_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_tax_declarations'
    )

    total_exemptions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxable_income = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    annual_tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monthly_tds = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ['employee', 'financial_year']
        ordering = ['-financial_year']

    def __str__(self):
        return f"{self.employee} - {self.financial_year}"

    def clean(self):
        super().clean()
        _assert_employee_org(self)
        _assert_employee_org(self, 'verified_by')


# =====================================================
# FULL & FINAL SETTLEMENT
# =====================================================

class FullFinalSettlement(OrganizationEntity):
    STATUS_DRAFT = 'draft'
    STATUS_PROCESSING = 'processing'
    STATUS_PENDING_APPROVAL = 'pending_approval'
    STATUS_APPROVED = 'approved'
    STATUS_PAID = 'paid'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_PENDING_APPROVAL, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_PAID, 'Paid'),
    ]

    employee = models.OneToOneField(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='fnf_settlement'
    )

    separation_date = models.DateField()
    last_working_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    pending_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    leave_encashment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gratuity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notice_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notice_recovery = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    loan_recovery = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tds = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    total_earnings = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_payable = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    breakdown = models.JSONField(default=dict)

    hr_approved = models.BooleanField(default=False)
    finance_approved = models.BooleanField(default=False)

    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_fnf'
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    def calculate_totals(self):
        earnings = [
            self.pending_salary,
            self.leave_encashment,
            self.gratuity,
            self.bonus,
            self.notice_pay,
            self.other_earnings
        ]

        deductions = [
            self.notice_recovery,
            self.loan_recovery,
            self.other_deductions,
            self.tds
        ]

        self.total_earnings = sum(earnings, Decimal('0.00'))
        self.total_deductions = sum(deductions, Decimal('0.00'))
        self.net_payable = self.total_earnings - self.total_deductions

    def save(self, *args, **kwargs):
        self.calculate_totals()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - F&F"


# =====================================================
# SALARY ARREARS
# =====================================================

class SalaryArrear(OrganizationEntity):
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='salary_arrears'
    )

    from_month = models.PositiveSmallIntegerField()
    from_year = models.PositiveSmallIntegerField()
    to_month = models.PositiveSmallIntegerField()
    to_year = models.PositiveSmallIntegerField()

    arrear_amount = models.DecimalField(max_digits=12, decimal_places=2)

    reason = models.TextField(blank=True)

    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.employee} - Arrear"


# =====================================================
# REIMBURSEMENTS
# =====================================================

class ReimbursementClaim(OrganizationEntity):
    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_PAID = 'paid'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PAID, 'Paid'),
    ]

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='reimbursements'
    )

    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)

    bill = models.FileField(upload_to='reimbursements/', null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.employee} - {self.title}"


# =====================================================
# EMPLOYEE LOAN
# =====================================================

class EmployeeLoan(OrganizationEntity):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_DISBURSED = 'disbursed'
    STATUS_REPAYING = 'repaying'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_DISBURSED, 'Disbursed'),
        (STATUS_REPAYING, 'Repaying'),
        (STATUS_CLOSED, 'Closed'),
    ]

    LOAN_TYPE_CHOICES = [
        ('salary_advance', 'Salary Advance'),
        ('personal', 'Personal Loan'),
        ('emergency', 'Emergency Loan'),
        ('education', 'Education Loan'),
        ('medical', 'Medical Loan'),
        ('other', 'Other'),
    ]

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='loans'
    )

    loan_type = models.CharField(max_length=20, choices=LOAN_TYPE_CHOICES, default='personal')
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tenure_months = models.PositiveIntegerField(help_text="Loan tenure in months")
    emi_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    total_repayable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_repaid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    outstanding_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reason = models.TextField(blank=True, help_text="Reason for loan request")

    applied_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_loans'
    )

    deduct_from_salary = models.BooleanField(default=True, help_text="Auto-deduct EMI from monthly salary")
    start_deduction_month = models.PositiveSmallIntegerField(null=True, blank=True)
    start_deduction_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-applied_at']

    def calculate_loan(self):
        if self.interest_rate > 0:
            monthly_rate = self.interest_rate / 100 / 12
            self.total_repayable = self.principal_amount * (1 + monthly_rate * self.tenure_months)
        else:
            self.total_repayable = self.principal_amount
        self.emi_amount = self.total_repayable / self.tenure_months if self.tenure_months > 0 else self.total_repayable
        self.outstanding_balance = self.total_repayable - self.amount_repaid

    def save(self, *args, **kwargs):
        self.calculate_loan()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - {self.loan_type} - {self.principal_amount}"


# =====================================================
# LOAN REPAYMENT
# =====================================================

class LoanRepayment(OrganizationEntity):
    loan = models.ForeignKey(
        EmployeeLoan,
        on_delete=models.CASCADE,
        related_name='repayments'
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    repayment_date = models.DateField()
    payslip = models.ForeignKey(
        Payslip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loan_repayments',
        help_text="Linked payslip if deducted from salary"
    )

    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-repayment_date']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.loan.amount_repaid = sum(
            r.amount for r in self.loan.repayments.all()
        )
        self.loan.outstanding_balance = self.loan.total_repayable - self.loan.amount_repaid
        if self.loan.outstanding_balance <= 0:
            self.loan.status = EmployeeLoan.STATUS_CLOSED
            self.loan.closed_at = timezone.now()
        self.loan.save(update_fields=['amount_repaid', 'outstanding_balance', 'status', 'closed_at'])

    def __str__(self):
        return f"{self.loan.employee} - Repayment {self.amount}"
