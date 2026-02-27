"""Authentication app filters."""
import django_filters
from .models import User
from .models_hierarchy import Branch, BranchUser


class UserFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(lookup_expr='icontains')
    first_name = django_filters.CharFilter(lookup_expr='icontains')
    last_name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    is_staff = django_filters.BooleanFilter()
    is_verified = django_filters.BooleanFilter()
    is_org_admin = django_filters.BooleanFilter()
    gender = django_filters.CharFilter()
    date_joined_after = django_filters.DateTimeFilter(field_name='date_joined', lookup_expr='gte')
    date_joined_before = django_filters.DateTimeFilter(field_name='date_joined', lookup_expr='lte')

    class Meta:
        model = User
        fields = ['email', 'is_active', 'is_staff', 'is_verified', 'is_org_admin', 'gender']


class BranchFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    branch_type = django_filters.ChoiceFilter(choices=[
        ('headquarters', 'Headquarters'), ('regional', 'Regional'),
        ('branch', 'Branch'), ('remote', 'Remote'),
    ])
    is_headquarters = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Branch
        fields = ['branch_type', 'is_headquarters', 'is_active']


class BranchUserFilter(django_filters.FilterSet):
    user = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    role = django_filters.ChoiceFilter(choices=[
        ('BRANCH_ADMIN', 'Branch Admin'), ('EMPLOYEE', 'Employee'),
    ])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = BranchUser
        fields = ['user', 'branch', 'role', 'is_active']
