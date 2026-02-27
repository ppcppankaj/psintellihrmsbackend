"""
Billing Serializers – Enterprise SaaS Subscription Engine
"""
from rest_framework import serializers

from .models import (
    BankDetails,
    Invoice,
    OrganizationBillingProfile,
    OrganizationSubscription,
    Payment,
    PaymentTransaction,
    Plan,
)
from .services import RenewalService, SubscriptionEnforcer


# ======================================================================
# Bank Details
# ======================================================================
class BankDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankDetails
        fields = [
            'id', 'organization', 'account_name', 'account_number',
            'bank_name', 'ifsc_code', 'swift_code', 'branch_name',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


# ======================================================================
# Plan (Global)
# ======================================================================
class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'code', 'description',
            'monthly_price', 'yearly_price',
            'max_employees', 'max_branches', 'storage_limit',
            'payroll_enabled', 'recruitment_enabled', 'attendance_enabled',
            'helpdesk_enabled', 'timesheet_enabled', 'document_enabled',
            'workflow_enabled', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ======================================================================
# Subscription
# ======================================================================
class OrganizationSubscriptionSerializer(serializers.ModelSerializer):
    plan_details = PlanSerializer(source='plan', read_only=True)
    grace_expires_on = serializers.SerializerMethodField()
    is_in_grace_period = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    renewal_link = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationSubscription
        fields = [
            'id', 'organization', 'plan', 'plan_details',
            'start_date', 'expiry_date', 'trial_end_date',
            'is_trial', 'is_active', 'grace_expires_on',
            'is_in_grace_period', 'is_expired', 'renewal_link',
            'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_grace_expires_on(self, obj):
        return obj.grace_expires_on

    def get_is_in_grace_period(self, obj):
        return obj.is_in_grace_period

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_renewal_link(self, obj):
        if not obj.organization_id:
            return None
        return RenewalService.build_renewal_url(obj.organization)

    def get_status(self, obj):
        """Frontend-friendly lifecycle status string."""
        if not obj.is_active:
            return 'suspended'
        if obj.is_trial:
            from django.utils import timezone
            if obj.trial_end_date and timezone.now().date() > obj.trial_end_date:
                return 'trial_expired'
            return 'trial'
        if obj.is_in_grace_period:
            return 'past_due'
        if obj.grace_period_lapsed:
            return 'expired'
        return 'active'


class SubscriptionDashboardSerializer(serializers.Serializer):
    """Aggregated billing dashboard payload for frontend."""
    subscription = OrganizationSubscriptionSerializer(read_only=True)
    usage = serializers.DictField(read_only=True)

    def to_representation(self, instance):
        organization = instance
        from .services import SubscriptionService
        sub = SubscriptionService.get_active_subscription(organization)
        usage = {}
        if sub:
            try:
                usage = SubscriptionEnforcer.usage_summary(organization)
            except Exception:
                usage = {}
        return {
            'subscription': OrganizationSubscriptionSerializer(sub).data if sub else None,
            'usage': usage,
        }


# ======================================================================
# Invoice
# ======================================================================
class InvoiceSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'organization', 'subscription', 'plan', 'plan_name',
            'invoice_number', 'amount', 'gst_percentage', 'gst_amount',
            'total_amount', 'billing_name', 'billing_address', 'gstin',
            'generated_at', 'due_date', 'paid_status', 'paid_at', 'pdf_file',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'organization', 'plan', 'plan_name',
            'generated_at', 'created_at', 'updated_at',
        ]


# ======================================================================
# Payments
# ======================================================================
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'organization', 'invoice', 'amount', 'payment_method',
            'transaction_id', 'status', 'gateway_response',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class PaymentTransactionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'organization', 'plan', 'plan_name', 'subscription',
            'amount', 'currency', 'status', 'razorpay_order_id',
            'razorpay_payment_id', 'razorpay_signature',
            'metadata', 'paid_at', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'organization', 'subscription', 'status',
            'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature',
            'metadata', 'paid_at', 'is_active', 'created_at', 'updated_at',
        ]


# ======================================================================
# Razorpay flow serializers
# ======================================================================
class CreatePaymentOrderSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_order_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class SubscribeSerializer(serializers.Serializer):
    """POST /billing/subscribe/ – select a plan to upgrade/switch."""
    plan_id = serializers.UUIDField()
    duration_days = serializers.IntegerField(required=False, min_value=1, default=30)


# ======================================================================
# Billing profile
# ======================================================================
class OrganizationBillingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationBillingProfile
        fields = [
            'id', 'organization', 'legal_name', 'billing_address', 'gstin',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


# ======================================================================
# Usage / metrics
# ======================================================================
class UsageCalculationSerializer(serializers.Serializer):
    """Usage calculation response."""
    subscription_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    billing_period_start = serializers.DateField()
    billing_period_end = serializers.DateField()
    employee_count = serializers.IntegerField()
    max_employees = serializers.IntegerField(allow_null=True)
    overage_count = serializers.IntegerField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    overage_charge = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
