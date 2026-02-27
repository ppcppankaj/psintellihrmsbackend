"""Payroll app filters."""
import django_filters
from .models import (
    EmployeeSalary, PayrollRun, Payslip, PFContribution,
    TaxDeclaration, FullFinalSettlement, SalaryArrear,
    ReimbursementClaim, EmployeeLoan, LoanRepayment,
)


class EmployeeSalaryFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    is_active = django_filters.BooleanFilter()
    effective_from = django_filters.DateFilter(lookup_expr='gte')
    effective_to = django_filters.DateFilter(lookup_expr='lte')

    class Meta:
        model = EmployeeSalary
        fields = ['employee', 'is_active']


class PayrollRunFilter(django_filters.FilterSet):
    branch = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('processing', 'Processing'), ('processed', 'Processed'),
        ('pending_approval', 'Pending Approval'), ('approved', 'Approved'),
        ('locked', 'Locked'), ('paid', 'Paid'),
    ])
    month = django_filters.NumberFilter()
    year = django_filters.NumberFilter()
    pay_date_from = django_filters.DateFilter(field_name='pay_date', lookup_expr='gte')
    pay_date_to = django_filters.DateFilter(field_name='pay_date', lookup_expr='lte')

    class Meta:
        model = PayrollRun
        fields = ['branch', 'status', 'month', 'year']


class PayslipFilter(django_filters.FilterSet):
    payroll_run = django_filters.UUIDFilter()
    employee = django_filters.UUIDFilter()

    class Meta:
        model = Payslip
        fields = ['payroll_run', 'employee']


class TaxDeclarationFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    tax_regime = django_filters.ChoiceFilter(choices=[('old', 'Old'), ('new', 'New')])
    proofs_submitted = django_filters.BooleanFilter()
    proofs_verified = django_filters.BooleanFilter()

    class Meta:
        model = TaxDeclaration
        fields = ['employee', 'tax_regime', 'proofs_submitted', 'proofs_verified']


class FullFinalSettlementFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('processing', 'Processing'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'), ('paid', 'Paid'),
    ])

    class Meta:
        model = FullFinalSettlement
        fields = ['employee', 'status']


class SalaryArrearFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    is_paid = django_filters.BooleanFilter()

    class Meta:
        model = SalaryArrear
        fields = ['employee', 'is_paid']


class ReimbursementClaimFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('submitted', 'Submitted'),
        ('approved', 'Approved'), ('rejected', 'Rejected'), ('paid', 'Paid'),
    ])

    class Meta:
        model = ReimbursementClaim
        fields = ['employee', 'status']


class EmployeeLoanFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'),
        ('disbursed', 'Disbursed'), ('repaying', 'Repaying'), ('closed', 'Closed'),
    ])
    loan_type = django_filters.CharFilter()

    class Meta:
        model = EmployeeLoan
        fields = ['employee', 'status', 'loan_type']


class LoanRepaymentFilter(django_filters.FilterSet):
    loan = django_filters.UUIDFilter()
    repayment_date_from = django_filters.DateFilter(field_name='repayment_date', lookup_expr='gte')
    repayment_date_to = django_filters.DateFilter(field_name='repayment_date', lookup_expr='lte')

    class Meta:
        model = LoanRepayment
        fields = ['loan']
