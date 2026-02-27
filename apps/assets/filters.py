"""Assets app filters."""
import django_filters
from .models import (
    AssetCategory, Asset, AssetAssignment,
    AssetMaintenance, AssetRequest,
)


class AssetCategoryFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AssetCategory
        fields = ['is_active']


class AssetFilter(django_filters.FilterSet):
    category = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    current_assignee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('available', 'Available'), ('assigned', 'Assigned'),
        ('maintenance', 'Maintenance'), ('retired', 'Retired'),
    ])
    is_active = django_filters.BooleanFilter()
    purchase_date_from = django_filters.DateFilter(field_name='purchase_date', lookup_expr='gte')
    purchase_date_to = django_filters.DateFilter(field_name='purchase_date', lookup_expr='lte')

    class Meta:
        model = Asset
        fields = ['category', 'branch', 'current_assignee', 'status', 'is_active']


class AssetAssignmentFilter(django_filters.FilterSet):
    asset = django_filters.UUIDFilter()
    employee = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    assigned_date_from = django_filters.DateFilter(field_name='assigned_date', lookup_expr='gte')

    class Meta:
        model = AssetAssignment
        fields = ['asset', 'employee', 'branch']


class AssetMaintenanceFilter(django_filters.FilterSet):
    asset = django_filters.UUIDFilter()
    maintenance_type = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('scheduled', 'Scheduled'), ('in_progress', 'In Progress'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])

    class Meta:
        model = AssetMaintenance
        fields = ['asset', 'maintenance_type', 'status']


class AssetRequestFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    category = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'),
        ('fulfilled', 'Fulfilled'), ('cancelled', 'Cancelled'),
    ])

    class Meta:
        model = AssetRequest
        fields = ['employee', 'category', 'status']
