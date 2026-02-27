from django.contrib import admin
from apps.core.admin_mixins import OrganizationAwareAdminMixin, BranchAwareAdminMixin
from .models import (
    ExpenseCategory, ExpenseClaim, ExpenseItem, ExpenseApproval,
    EmployeeAdvance, AdvanceSettlement
)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'max_limit_per_claim', 'requires_receipt', 'is_active']
    list_filter = ['is_active', 'requires_receipt', 'requires_approval']
    search_fields = ['name', 'code']
    ordering = ['display_order', 'name']


class ExpenseItemInline(admin.TabularInline):
    model = ExpenseItem
    extra = 0
    fields = ['category', 'expense_date', 'description', 'claimed_amount', 'approved_amount', 'is_approved']
    readonly_fields = ['approved_amount', 'is_approved']


class ExpenseApprovalInline(admin.TabularInline):
    model = ExpenseApproval
    extra = 0
    fields = ['level', 'approver', 'action', 'comments', 'created_at']
    readonly_fields = ['created_at']


@admin.register(ExpenseClaim)
class ExpenseClaimAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = [
        'claim_number', 'employee', 'title', 'claim_date',
        'total_claimed_amount', 'total_approved_amount', 'status', 'payment_status'
    ]
    list_filter = ['status', 'payment_status', 'claim_date']
    search_fields = ['claim_number', 'employee__employee_id', 'title']
    readonly_fields = [
        'claim_number', 'total_claimed_amount', 'total_approved_amount', 'total_paid_amount'
    ]
    inlines = [ExpenseItemInline, ExpenseApprovalInline]
    date_hierarchy = 'claim_date'
    
    fieldsets = (
        ('Claim Details', {
            'fields': ('claim_number', 'employee', 'title', 'description')
        }),
        ('Dates', {
            'fields': ('claim_date', 'expense_from', 'expense_to')
        }),
        ('Amounts', {
            'fields': ('total_claimed_amount', 'total_approved_amount', 'total_paid_amount', 'advance_adjusted')
        }),
        ('Status', {
            'fields': ('status', 'payment_status', 'current_approver')
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at', 'rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Payment', {
            'fields': ('paid_by', 'paid_at', 'payment_mode', 'payment_reference'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ExpenseItem)
class ExpenseItemAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['claim', 'category', 'expense_date', 'claimed_amount', 'approved_amount', 'is_approved']
    list_filter = ['is_approved', 'category', 'expense_date']
    search_fields = ['claim__claim_number', 'description', 'vendor_name']


class AdvanceSettlementInline(admin.TabularInline):
    model = AdvanceSettlement
    extra = 0
    fields = ['settlement_type', 'amount', 'settlement_date', 'expense_claim', 'payslip']
    readonly_fields = ['expense_claim', 'payslip']


@admin.register(EmployeeAdvance)
class EmployeeAdvanceAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = [
        'advance_number', 'employee', 'amount', 'advance_date',
        'remaining_balance', 'status', 'settlement_type'
    ]
    list_filter = ['status', 'settlement_type', 'advance_date']
    search_fields = ['advance_number', 'employee__employee_id', 'purpose']
    readonly_fields = ['advance_number', 'amount_settled', 'remaining_balance']
    inlines = [AdvanceSettlementInline]
    date_hierarchy = 'advance_date'
    
    fieldsets = (
        ('Advance Details', {
            'fields': ('advance_number', 'employee', 'purpose', 'advance_date', 'amount')
        }),
        ('Settlement', {
            'fields': ('settlement_type', 'amount_settled', 'remaining_balance')
        }),
        ('Salary Deduction', {
            'fields': ('deduction_start_month', 'monthly_deduction_amount'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at', 'rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Disbursement', {
            'fields': ('disbursed_by', 'disbursed_at', 'disbursement_mode', 'disbursement_reference'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AdvanceSettlement)
class AdvanceSettlementAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['advance', 'settlement_type', 'amount', 'settlement_date']
    list_filter = ['settlement_type', 'settlement_date']
    search_fields = ['advance__advance_number']
