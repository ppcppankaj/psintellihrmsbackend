from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import EnterpriseModel, OrganizationEntity

class BankDetails(OrganizationEntity):
    """Admin Bank Details for receiving payments - Organization-specific"""
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    bank_name = models.CharField(max_length=255)
    ifsc_code = models.CharField(max_length=20)
    swift_code = models.CharField(max_length=20, blank=True, null=True)
    branch_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Bank Details"

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class Plan(EnterpriseModel):
    """Subscription plans - Global, managed by superadmin"""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    yearly_price = models.DecimalField(max_digits=10, decimal_places=2)

    max_employees = models.PositiveIntegerField(null=True, blank=True)
    max_branches = models.PositiveIntegerField(null=True, blank=True)
    storage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Storage limit in MB for uploaded documents",
    )

    payroll_enabled = models.BooleanField(default=True)
    recruitment_enabled = models.BooleanField(default=True)
    attendance_enabled = models.BooleanField(default=True)
    helpdesk_enabled = models.BooleanField(default=True)
    timesheet_enabled = models.BooleanField(default=True)
    document_enabled = models.BooleanField(default=True)
    workflow_enabled = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['monthly_price']

    def __str__(self):
        return self.name

class OrganizationSubscription(OrganizationEntity):
    """Organization subscriptions"""

    GRACE_PERIOD_DEFAULT = 3

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    start_date = models.DateField()
    expiry_date = models.DateField()
    trial_end_date = models.DateField(null=True, blank=True)
    is_trial = models.BooleanField(default=True)
    grace_period_days = models.PositiveSmallIntegerField(default=GRACE_PERIOD_DEFAULT)
    reminder_sent_3_days_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_1_day_at = models.DateTimeField(null=True, blank=True)
    expired_notice_sent_at = models.DateTimeField(null=True, blank=True)
    grace_notice_sent_at = models.DateTimeField(null=True, blank=True)
    suspension_notice_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(
                fields=['organization'],
                condition=Q(is_active=True),
                name='uq_active_subscription_per_org',
            )
        ]

    def __str__(self):
        return f"{self.organization} → {self.plan.name}"

    @property
    def is_expired(self):
        today = timezone.now().date()
        if self.is_trial and self.trial_end_date:
            return today > self.trial_end_date
        return today > self.expiry_date

    def deactivate(self, reason=None):
        if not self.is_active:
            return
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])
        if self.organization_id:
            org = self.organization
            org.subscription_status = 'suspended'
            org.save(update_fields=['subscription_status', 'updated_at'])

    def _sync_organization_fields(self):
        if not self.organization_id:
            return
        org = self.organization
        today = timezone.now().date()
        if not self.is_active:
            org.subscription_status = 'suspended'
        elif self.is_trial:
            org.subscription_status = 'trial'
        elif self.expiry_date and self.expiry_date < today <= self.grace_expires_on:
            org.subscription_status = 'past_due'
        else:
            org.subscription_status = 'active'
        if self.trial_end_date:
            org.trial_ends_at = timezone.make_aware(
                datetime.combine(self.trial_end_date, time.max),
                timezone.get_current_timezone(),
            )
        else:
            org.trial_ends_at = None
        org.save(update_fields=['subscription_status', 'trial_ends_at', 'updated_at'])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self._sync_organization_fields()

    @property
    def grace_expires_on(self):
        if not self.expiry_date:
            return None
        return self.expiry_date + timedelta(days=self.grace_period_days or self.GRACE_PERIOD_DEFAULT)

    @property
    def is_in_grace_period(self):
        if not self.expiry_date or not self.is_active:
            return False
        today = timezone.now().date()
        grace_end = self.grace_expires_on
        return self.expiry_date < today <= grace_end

    @property
    def grace_period_lapsed(self):
        if not self.expiry_date or not self.is_active:
            return False
        today = timezone.now().date()
        grace_end = self.grace_expires_on
        return today > grace_end

class OrganizationBillingProfile(OrganizationEntity):
    """Stores GST billing details per organization"""

    legal_name = models.CharField(max_length=255)
    billing_address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)

    class Meta:
        verbose_name = "Organization Billing Profile"
        verbose_name_plural = "Organization Billing Profiles"
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                name="uq_billing_profile_per_org",
            )
        ]

    def __str__(self):
        return f"{self.organization} Billing Profile"


class Invoice(OrganizationEntity):
    """Billing invoices - Organization-specific"""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_OVERDUE = 'overdue'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_OVERDUE, 'Overdue'),
    ]

    subscription = models.ForeignKey(
        OrganizationSubscription,
        on_delete=models.CASCADE,
        related_name='invoices',
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    billing_name = models.CharField(max_length=255)
    billing_address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()
    paid_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(upload_to='invoices/', null=True, blank=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if not self.organization_id and self.subscription_id:
            self.organization = self.subscription.organization
        if not self.plan_id and self.subscription_id:
            self.plan = self.subscription.plan
        super().save(*args, **kwargs)

class Payment(OrganizationEntity):
    """Payment transactions - Organization-specific"""
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    transaction_id = models.CharField(max_length=100, unique=True)
    
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed'), ('refunded', 'Refunded')
    ])
    
    gateway_response = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.amount}"
    
    def save(self, *args, **kwargs):
        """Auto-set organization from invoice"""
        if not self.organization_id and self.invoice_id:
            self.organization = self.invoice.organization
        super().save(*args, **kwargs)


class PaymentTransaction(OrganizationEntity):
    """Tracks Razorpay payment attempts for plan purchases"""

    STATUS_CREATED = 'created'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_CREATED, 'Created'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    subscription = models.ForeignKey(
        OrganizationSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name='payment_transactions',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        plan_name = self.plan.name if self.plan_id else 'Unknown plan'
        return f"{self.organization} → {plan_name} ({self.status})"


# Backwards compatibility alias
Subscription = OrganizationSubscription
