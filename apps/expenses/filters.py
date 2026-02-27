"""Expenses app filters."""
import django_filters
from .models import (
    ExpenseCategory, ExpenseClaim, ExpenseItem,
    ExpenseApproval, EmployeeAdvance, AdvanceSettlement,
)


class ExpenseCategoryFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    requires_receipt = django_filters.BooleanFilter()
    requires_approval = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = ExpenseCategory
        fields = ['requires_receipt', 'requires_approval', 'is_active']


class ExpenseClaimFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('submitted', 'Submitted'),
        ('pending_approval', 'Pending Approval'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('paid', 'Paid'), ('cancelled', 'Cancelled'),
    ])
    payment_status = django_filters.CharFilter()
    claim_date_from = django_filters.DateFilter(field_name='claim_date', lookup_expr='gte')
    claim_date_to = django_filters.DateFilter(field_name='claim_date', lookup_expr='lte')

    class Meta:
        model = ExpenseClaim
        fields = ['employee', 'status', 'payment_status']


class ExpenseItemFilter(django_filters.FilterSet):
    claim = django_filters.UUIDFilter()
    category = django_filters.UUIDFilter()
    expense_date = django_filters.DateFilter()
    is_approved = django_filters.BooleanFilter()

    class Meta:
        model = ExpenseItem
        fields = ['claim', 'category', 'is_approved']


class ExpenseApprovalFilter(django_filters.FilterSet):
    claim = django_filters.UUIDFilter()
    approver = django_filters.UUIDFilter()
    action = django_filters.CharFilter()

    class Meta:
        model = ExpenseApproval
        fields = ['claim', 'approver', 'action']


class EmployeeAdvanceFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('disbursed', 'Disbursed'),
        ('settled', 'Settled'), ('cancelled', 'Cancelled'),
    ])

    class Meta:
        model = EmployeeAdvance
        fields = ['employee', 'status']


class AdvanceSettlementFilter(django_filters.FilterSet):
    advance = django_filters.UUIDFilter()
    settlement_type = django_filters.CharFilter()
    settlement_date = django_filters.DateFilter()

    class Meta:
        model = AdvanceSettlement
        fields = ['advance', 'settlement_type']
