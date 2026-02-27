"""Billing Admin"""

from django.contrib import admin

from apps.core.admin_mixins import OrganizationAwareAdminMixin

from .models import (
    BankDetails,
    Invoice,
    OrganizationBillingProfile,
    OrganizationSubscription,
    Payment,
    PaymentTransaction,
    Plan,
)


@admin.register(BankDetails)
class BankDetailsAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['account_name', 'account_number', 'bank_name', 'branch_name', 'is_active']
    list_filter = ['is_active', 'bank_name']
    search_fields = ['account_name', 'account_number', 'bank_name']


def is_org_admin(user):
    """Safely check if user is an org admin (handles AnonymousUser)"""
    return user.is_authenticated and getattr(user, 'is_org_admin', False)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Plans management - SUPERADMIN ONLY"""
    
    list_display = (
        "name",
        "code",
        "monthly_price",
        "yearly_price",
        "max_employees",
        "max_branches",
        "storage_limit",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    
    def has_module_permission(self, request):
        """Only superadmin can access Plans"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        """Only superadmin can view Plans"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_add_permission(self, request):
        """Only superadmin can create Plans"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        """Only superadmin can edit Plans"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        """Only superadmin can delete Plans"""
        return request.user.is_authenticated and request.user.is_superuser


@admin.register(OrganizationSubscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Subscriptions - ORG ADMIN can view/edit their own organization's subscription"""
    
    list_display = (
        "organization",
        "plan",
        "start_date",
        "expiry_date",
        "trial_end_date",
        "is_trial",
        "is_active",
    )
    list_filter = ("is_trial", "is_active", "plan")
    raw_id_fields = ("organization", "plan")
    
    def get_queryset(self, request):
        """Filter subscriptions by organization for org admins"""
        qs = super().get_queryset(request)
        
        if not request.user.is_authenticated:
            return qs.none()
        
        if request.user.is_superuser:
            return qs
        
        # Org admin can only see their organization's subscription
        if is_org_admin(request.user):
            user_org = request.user.get_organization()
            if user_org:
                return qs.filter(organization=user_org)
        
        return qs.none()
    
    def has_module_permission(self, request):
        """Superadmin and org admins can access Subscriptions"""
        if not request.user.is_authenticated:
            return False
        return request.user.is_superuser or is_org_admin(request.user)
    
    def has_view_permission(self, request, obj=None):
        """Superadmin and org admins can view subscriptions"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if is_org_admin(request.user):
            if obj is None:
                return True
            user_org = request.user.get_organization()
            return user_org and obj.organization_id == user_org.id
        return False
    
    def has_change_permission(self, request, obj=None):
        """Superadmin and org admins can edit their subscription"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if is_org_admin(request.user):
            if obj is None:
                return True
            user_org = request.user.get_organization()
            return user_org and obj.organization_id == user_org.id
        return False
    
    def has_add_permission(self, request):
        """Only superadmin can create subscriptions"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        """Only superadmin can delete subscriptions"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def get_readonly_fields(self, request, obj=None):
        """Org admins can only view, most fields are readonly"""
        readonly = list(super().get_readonly_fields(request, obj))
        
        if request.user.is_authenticated and not request.user.is_superuser and is_org_admin(request.user):
            # Org admin can only view subscription, not change critical fields
            readonly.extend(['organization', 'plan', 'start_date', 'expiry_date', 'trial_end_date', 'is_trial'])
        
        return readonly


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Invoices - ORG ADMIN can view their organization's invoices"""
    
    list_display = (
        "invoice_number",
        "subscription",
        "total_amount",
        "paid_status",
        "due_date",
        "paid_at",
    )
    list_filter = ("paid_status",)
    search_fields = ("invoice_number", "billing_name", "gstin")
    raw_id_fields = ("subscription", "plan")
    
    def get_queryset(self, request):
        """Filter invoices by organization for org admins"""
        qs = super().get_queryset(request)
        
        if not request.user.is_authenticated:
            return qs.none()
        
        if request.user.is_superuser:
            return qs
        
        # Org admin can only see their organization's invoices
        if is_org_admin(request.user):
            user_org = request.user.get_organization()
            if user_org:
                return qs.filter(subscription__organization=user_org)
        
        return qs.none()
    
    def has_module_permission(self, request):
        """Superadmin and org admins can access Invoices"""
        if not request.user.is_authenticated:
            return False
        return request.user.is_superuser or is_org_admin(request.user)
    
    def has_view_permission(self, request, obj=None):
        """Superadmin and org admins can view invoices"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if is_org_admin(request.user):
            if obj is None:
                return True
            user_org = request.user.get_organization()
            return user_org and obj.subscription.organization_id == user_org.id
        return False
    
    def has_add_permission(self, request):
        """Only superadmin can create invoices"""
        return request.user.is_authenticated and request.user.is_superuser


@admin.register(OrganizationBillingProfile)
class OrganizationBillingProfileAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ("organization", "legal_name", "gstin", "updated_at")
    search_fields = ("organization__name", "legal_name", "gstin")
    readonly_fields = ("organization",)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "plan",
        "amount",
        "currency",
        "status",
        "razorpay_order_id",
        "paid_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("razorpay_order_id", "razorpay_payment_id")
    raw_id_fields = ("organization", "plan", "subscription")
    
    def has_change_permission(self, request, obj=None):
        """Only superadmin can edit invoices"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        """Only superadmin can delete invoices"""
        return request.user.is_authenticated and request.user.is_superuser


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Payments - ORG ADMIN can add/view payments for their organization's invoices"""
    
    list_display = (
        "invoice",
        "amount",
        "payment_method",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_method")
    raw_id_fields = ("invoice",)
    
    def get_queryset(self, request):
        """Filter payments by organization for org admins"""
        qs = super().get_queryset(request)
        
        if not request.user.is_authenticated:
            return qs.none()
        
        if request.user.is_superuser:
            return qs
        
        # Org admin can only see their organization's payments
        if is_org_admin(request.user):
            user_org = request.user.get_organization()
            if user_org:
                return qs.filter(invoice__subscription__organization=user_org)
        
        return qs.none()
    
    def has_module_permission(self, request):
        """Superadmin and org admins can access Payments"""
        if not request.user.is_authenticated:
            return False
        return request.user.is_superuser or is_org_admin(request.user)
    
    def has_view_permission(self, request, obj=None):
        """Superadmin and org admins can view payments"""
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if is_org_admin(request.user):
            if obj is None:
                return True
            user_org = request.user.get_organization()
            return user_org and obj.invoice.subscription.organization_id == user_org.id
        return False
    
    def has_add_permission(self, request):
        """Superadmin and org admins can add payments"""
        if not request.user.is_authenticated:
            return False
        return request.user.is_superuser or is_org_admin(request.user)
    
    def has_change_permission(self, request, obj=None):
        """Only superadmin can edit payments after creation"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        """Only superadmin can delete payments"""
        return request.user.is_authenticated and request.user.is_superuser
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter invoice choices for org admins"""
        if db_field.name == 'invoice' and request.user.is_authenticated and not request.user.is_superuser:
            if is_org_admin(request.user):
                user_org = request.user.get_organization()
                if user_org:
                    from .models import Invoice
                    kwargs['queryset'] = Invoice.objects.filter(subscription__organization=user_org)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
