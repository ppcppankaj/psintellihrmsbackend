"""
Payroll Admin
"""

from django.contrib import admin
from apps.core.admin_mixins import BranchAwareAdminMixin, OrganizationAwareAdminMixin
from .models import (
    EmployeeSalary, PayrollRun, Payslip, PFContribution,
    TaxDeclaration, FullFinalSettlement
)

@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    def log_addition(self, *args, **kwargs):
        pass
    def log_change(self, *args, **kwargs):
        pass
    def log_deletion(self, *args, **kwargs):
        pass
    list_display = ['employee', 'annual_ctc', 'monthly_gross', 'net_salary', 'effective_from']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee']
    fieldsets = (
        ('Basic Info', {
            'fields': ('employee', 'effective_from')
        }),
        ('Totals', {
            'fields': ('annual_ctc', 'monthly_gross', 'net_salary')
        }),
        ('Earnings', {
            'fields': (
                'basic', 'hra', 'special_allowance', 'conveyance', 
                'medical_allowance', 'lta', 'performance_bonus'
            )
        }),
        ('Deductions', {
            'fields': ('pf_employee', 'esi_employee', 'professional_tax')
        }),
        ('Employer Contributions', {
            'fields': ('pf_employer', 'esi_employer', 'gratuity')
        }),
    )

class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0
    readonly_fields = ['employee', 'gross_salary', 'total_deductions', 'net_salary']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PayrollRun)
class PayrollRunAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    def log_addition(self, *args, **kwargs):
        pass
    def log_change(self, *args, **kwargs):
        pass
    def log_deletion(self, *args, **kwargs):
        pass
    list_display = ['name', 'month', 'year', 'branch', 'status', 'total_employees', 'total_net', 'pay_date']
    list_filter = ['status', 'year', 'month', 'branch']
    search_fields = ['name']
    raw_id_fields = ['branch']
    ordering = ['-year', '-month']
    inlines = [PayslipInline]


@admin.register(Payslip)
class PayslipAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    def log_addition(self, *args, **kwargs):
        pass
    def log_change(self, *args, **kwargs):
        pass
    def log_deletion(self, *args, **kwargs):
        pass
    list_display = ['employee', 'payroll_run', 'gross_salary', 'total_deductions', 'net_salary']
    list_filter = ['payroll_run', 'payroll_run__year', 'payroll_run__month']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee', 'payroll_run']
    readonly_fields = ['earnings_breakdown', 'deductions_breakdown']


@admin.register(PFContribution)
class PFContributionAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    def log_addition(self, *args, **kwargs):
        pass
    def log_change(self, *args, **kwargs):
        pass
    def log_deletion(self, *args, **kwargs):
        pass
    list_display = ['payslip', 'uan', 'epf_employee', 'epf_employer', 'eps', 'pf_wages']
    search_fields = ['payslip__employee__employee_id', 'uan', 'pf_number']
    raw_id_fields = ['payslip']


@admin.register(TaxDeclaration)
class TaxDeclarationAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    def log_addition(self, *args, **kwargs):
        pass
    def log_change(self, *args, **kwargs):
        pass
    def log_deletion(self, *args, **kwargs):
        pass
    list_display = ['employee', 'financial_year', 'tax_regime', 'total_exemptions', 'proofs_submitted', 'proofs_verified']
    list_filter = ['financial_year', 'tax_regime', 'proofs_submitted', 'proofs_verified']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee', 'verified_by']


@admin.register(FullFinalSettlement)
class FullFinalSettlementAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    def log_addition(self, *args, **kwargs):
        pass
    def log_change(self, *args, **kwargs):
        pass
    def log_deletion(self, *args, **kwargs):
        pass
    list_display = ['employee', 'separation_date', 'status', 'total_earnings', 'total_deductions', 'net_payable']
    list_filter = ['status', 'separation_date']
    search_fields = ['employee__employee_id', 'employee__user__email']
    raw_id_fields = ['employee', 'approved_by']
