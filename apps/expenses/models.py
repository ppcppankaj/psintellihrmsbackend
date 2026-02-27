"""
Expense Models - Expense Claims & Employee Advances

Inspired by Frappe HRMS expense management:
- Expense categories with limits
- Multi-item expense claims
- Receipt attachments
- Multi-level approval workflows
- Employee advances with payroll integration
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from apps.core.models import OrganizationEntity


class ExpenseCategory(OrganizationEntity):
    """
    Expense category definitions.
    Examples: Travel, Accommodation, Food, Office Supplies, etc.
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    
    # Limits and policies
    max_limit_per_claim = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Maximum amount allowed per single claim"
    )
    max_monthly_limit = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Maximum total amount per month"
    )
    
    # Requirements
    requires_receipt = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)
    min_amount_for_receipt = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0'),
        help_text="Minimum amount above which receipt is mandatory"
    )
    
    # Accounting integration
    gl_account = models.CharField(max_length=50, blank=True, help_text="GL Account code for accounting")
    cost_center = models.CharField(max_length=50, blank=True)
    
    # Designation-based limits (JSON: {designation_id: max_amount})
    designation_limits = models.JSONField(default=dict, blank=True)
    
    display_order = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Expense Categories'
    
    def __str__(self):
        return self.name


class ExpenseClaim(OrganizationEntity):
    """
    Main expense claim record.
    Contains multiple expense items.
    """
    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_PENDING_APPROVAL = 'pending_approval'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_PENDING_APPROVAL, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PAID, 'Paid'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    PAYMENT_NOT_PAID = 'not_paid'
    PAYMENT_PARTIALLY_PAID = 'partially_paid'
    PAYMENT_PAID = 'paid'
    
    PAYMENT_CHOICES = [
        (PAYMENT_NOT_PAID, 'Not Paid'),
        (PAYMENT_PARTIALLY_PAID, 'Partially Paid'),
        (PAYMENT_PAID, 'Paid'),
    ]
    
    # Claim identification
    claim_number = models.CharField(max_length=20, unique=True, editable=False)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='expense_claims'
    )
    
    # Claim details
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    claim_date = models.DateField()
    
    # Expense period
    expense_from = models.DateField()
    expense_to = models.DateField()
    
    # Amounts
    total_claimed_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    total_approved_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    total_paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_NOT_PAID)
    
    # Approval workflow
    current_approver = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pending_expense_approvals'
    )
    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_expenses'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Payment details
    paid_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processed_expense_payments'
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_mode = models.CharField(
        max_length=20,
        choices=[
            ('bank_transfer', 'Bank Transfer'),
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('wallet', 'Wallet'),
        ],
        blank=True
    )
    
    # Advance adjustment
    advance_adjusted = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0'),
        help_text="Amount adjusted against employee advance"
    )
    
    class Meta:
        ordering = ['-claim_date', '-created_at']
    
    def __str__(self):
        return f"{self.claim_number} - {self.employee.employee_id}"
    
    def save(self, *args, **kwargs):
        if not self.claim_number:
            self.claim_number = self._generate_claim_number()
        super().save(*args, **kwargs)
    
    def _generate_claim_number(self):
        """Generate unique claim number"""
        from django.utils import timezone
        import random
        year = timezone.now().year
        random_suffix = random.randint(1000, 9999)
        return f"EXP-{year}-{random_suffix}"
    
    def update_totals(self):
        """Update total amounts based on expense items"""
        items = self.items.all()
        self.total_claimed_amount = sum(item.claimed_amount for item in items)
        self.total_approved_amount = sum(item.approved_amount or item.claimed_amount for item in items if item.is_approved)
        self.save(update_fields=['total_claimed_amount', 'total_approved_amount'])


class ExpenseItem(OrganizationEntity):
    """
    Individual expense line item within a claim.
    """
    claim = models.ForeignKey(
        ExpenseClaim,
        on_delete=models.CASCADE,
        related_name='items'
    )
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name='expense_items'
    )
    
    # Expense details
    expense_date = models.DateField()
    description = models.CharField(max_length=500)
    
    # Amounts
    claimed_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    approved_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )
    
    # Receipt
    receipt = models.FileField(upload_to='expense_receipts/', null=True, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True, help_text="Invoice/Receipt number")
    
    # Vendor/Merchant
    vendor_name = models.CharField(max_length=200, blank=True)
    
    # Status
    is_approved = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    
    # Additional metadata
    currency = models.CharField(max_length=3, default='INR')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('1'))
    
    class Meta:
        ordering = ['expense_date']
    
    def __str__(self):
        return f"{self.category.name}: {self.claimed_amount}"


class ExpenseApproval(OrganizationEntity):
    """
    Approval history for expense claims.
    """
    claim = models.ForeignKey(
        ExpenseClaim,
        on_delete=models.CASCADE,
        related_name='approvals'
    )
    approver = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        related_name='expense_approvals'
    )
    
    level = models.PositiveSmallIntegerField(default=1)
    action = models.CharField(max_length=20, choices=[
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('forwarded', 'Forwarded'),
        ('returned', 'Returned for Clarification'),
    ])
    comments = models.TextField(blank=True)
    
    class Meta:
        ordering = ['level', 'created_at']
    
    def __str__(self):
        return f"{self.claim.claim_number} - Level {self.level} - {self.action}"


class EmployeeAdvance(OrganizationEntity):
    """
    Employee cash advances.
    Can be adjusted against future expense claims or salary.
    """
    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_DISBURSED = 'disbursed'
    STATUS_SETTLED = 'settled'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_DISBURSED, 'Disbursed'),
        (STATUS_SETTLED, 'Settled'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    SETTLEMENT_EXPENSE = 'expense'
    SETTLEMENT_SALARY = 'salary'
    SETTLEMENT_MIXED = 'mixed'
    
    SETTLEMENT_CHOICES = [
        (SETTLEMENT_EXPENSE, 'Against Expense Claims'),
        (SETTLEMENT_SALARY, 'Against Salary'),
        (SETTLEMENT_MIXED, 'Mixed'),
    ]
    
    # Advance identification
    advance_number = models.CharField(max_length=20, unique=True, editable=False)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='advances'
    )
    
    # Advance details
    purpose = models.TextField()
    advance_date = models.DateField()
    
    # Amount
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('1'))]
    )
    
    # Settlement tracking
    settlement_type = models.CharField(max_length=20, choices=SETTLEMENT_CHOICES, default=SETTLEMENT_EXPENSE)
    amount_settled = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0')
    )
    remaining_balance = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0')
    )
    
    # Salary deduction settings
    deduction_start_month = models.DateField(null=True, blank=True)
    monthly_deduction_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    # Approval
    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_advances'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Disbursement
    disbursed_at = models.DateTimeField(null=True, blank=True)
    disbursed_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='disbursed_advances'
    )
    disbursement_reference = models.CharField(max_length=100, blank=True)
    disbursement_mode = models.CharField(
        max_length=20,
        choices=[
            ('bank_transfer', 'Bank Transfer'),
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
        ],
        blank=True
    )
    
    class Meta:
        ordering = ['-advance_date', '-created_at']
    
    def __str__(self):
        return f"{self.advance_number} - {self.employee.employee_id}"
    
    def save(self, *args, **kwargs):
        if not self.advance_number:
            self.advance_number = self._generate_advance_number()
        if not self.remaining_balance:
            self.remaining_balance = self.amount
        super().save(*args, **kwargs)
    
    def _generate_advance_number(self):
        """Generate unique advance number"""
        from django.utils import timezone
        import random
        year = timezone.now().year
        random_suffix = random.randint(1000, 9999)
        return f"ADV-{year}-{random_suffix}"


class AdvanceSettlement(OrganizationEntity):
    """
    Track settlements against employee advances.
    """
    SETTLEMENT_EXPENSE = 'expense_claim'
    SETTLEMENT_SALARY = 'salary_deduction'
    SETTLEMENT_REFUND = 'refund'
    
    TYPE_CHOICES = [
        (SETTLEMENT_EXPENSE, 'Expense Claim Adjustment'),
        (SETTLEMENT_SALARY, 'Salary Deduction'),
        (SETTLEMENT_REFUND, 'Cash Refund'),
    ]
    
    advance = models.ForeignKey(
        EmployeeAdvance,
        on_delete=models.CASCADE,
        related_name='settlements'
    )
    
    settlement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    settlement_date = models.DateField()
    
    # References
    expense_claim = models.ForeignKey(
        ExpenseClaim,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='advance_settlements'
    )
    payslip = models.ForeignKey(
        'payroll.Payslip',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='advance_settlements'
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-settlement_date']
    
    def __str__(self):
        return f"{self.advance.advance_number} - {self.amount}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update advance remaining balance
        self.advance.amount_settled = self.advance.settlements.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        self.advance.remaining_balance = self.advance.amount - self.advance.amount_settled
        if self.advance.remaining_balance <= 0:
            self.advance.status = EmployeeAdvance.STATUS_SETTLED
        self.advance.save(update_fields=['amount_settled', 'remaining_balance', 'status'])
