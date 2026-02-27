"""Billing app filters."""
import django_filters
from .models import (
    Plan, OrganizationSubscription, Invoice, Payment,
    PaymentTransaction, OrganizationBillingProfile, BankDetails,
)


class PlanFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    payroll_enabled = django_filters.BooleanFilter()
    recruitment_enabled = django_filters.BooleanFilter()
    attendance_enabled = django_filters.BooleanFilter()

    class Meta:
        model = Plan
        fields = ['is_active', 'payroll_enabled', 'recruitment_enabled', 'attendance_enabled']


class OrganizationSubscriptionFilter(django_filters.FilterSet):
    plan = django_filters.UUIDFilter()
    is_trial = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    start_date_from = django_filters.DateFilter(field_name='start_date', lookup_expr='gte')
    expiry_date_to = django_filters.DateFilter(field_name='expiry_date', lookup_expr='lte')

    class Meta:
        model = OrganizationSubscription
        fields = ['plan', 'is_trial', 'is_active']


class InvoiceFilter(django_filters.FilterSet):
    subscription = django_filters.UUIDFilter()
    plan = django_filters.UUIDFilter()
    paid_status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue'),
    ])
    due_date_from = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_date_to = django_filters.DateFilter(field_name='due_date', lookup_expr='lte')

    class Meta:
        model = Invoice
        fields = ['subscription', 'plan', 'paid_status']


class PaymentFilter(django_filters.FilterSet):
    invoice = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('success', 'Success'),
        ('failed', 'Failed'), ('refunded', 'Refunded'),
    ])

    class Meta:
        model = Payment
        fields = ['invoice', 'status']


class PaymentTransactionFilter(django_filters.FilterSet):
    subscription = django_filters.UUIDFilter()
    plan = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('created', 'Created'), ('success', 'Success'), ('failed', 'Failed'),
    ])

    class Meta:
        model = PaymentTransaction
        fields = ['subscription', 'plan', 'status']


class OrganizationBillingProfileFilter(django_filters.FilterSet):
    organization = django_filters.UUIDFilter()

    class Meta:
        model = OrganizationBillingProfile
        fields = ['organization']


class BankDetailsFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = BankDetails
        fields = ['is_active']
