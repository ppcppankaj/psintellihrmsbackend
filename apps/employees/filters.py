"""Employee app filters."""
import django_filters
from .models import (
    Employee, Department, Designation, Location,
    EmployeeAddress, EmployeeBankAccount, EmergencyContact,
    EmployeeDependent, Skill, EmployeeSkill,
    EmploymentHistory, Document, Certification,
    EmployeeTransfer, EmployeePromotion, ResignationRequest,
    ExitInterview, SeparationChecklist,
)


class EmployeeFilter(django_filters.FilterSet):
    employee_id = django_filters.CharFilter(lookup_expr='icontains')
    first_name = django_filters.CharFilter(lookup_expr='icontains')
    last_name = django_filters.CharFilter(lookup_expr='icontains')
    email = django_filters.CharFilter(field_name='user__email', lookup_expr='icontains')
    department = django_filters.UUIDFilter()
    designation = django_filters.UUIDFilter()
    location = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    reporting_manager = django_filters.UUIDFilter()
    employment_type = django_filters.ChoiceFilter(choices=[
        ('full_time', 'Full Time'), ('part_time', 'Part Time'),
        ('contract', 'Contract'), ('intern', 'Intern'), ('consultant', 'Consultant'),
    ])
    employment_status = django_filters.ChoiceFilter(choices=[
        ('active', 'Active'), ('probation', 'Probation'),
        ('notice_period', 'Notice Period'), ('inactive', 'Inactive'),
        ('terminated', 'Terminated'),
    ])
    work_mode = django_filters.ChoiceFilter(choices=[
        ('office', 'Office'), ('remote', 'Remote'), ('hybrid', 'Hybrid'),
    ])
    is_active = django_filters.BooleanFilter()
    joined_after = django_filters.DateFilter(field_name='date_of_joining', lookup_expr='gte')
    joined_before = django_filters.DateFilter(field_name='date_of_joining', lookup_expr='lte')

    class Meta:
        model = Employee
        fields = [
            'department', 'designation', 'location', 'branch',
            'employment_type', 'employment_status', 'work_mode', 'is_active',
        ]


class DepartmentFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    branch = django_filters.UUIDFilter()
    parent = django_filters.UUIDFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Department
        fields = ['name', 'branch', 'parent', 'is_active']


class DesignationFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Designation
        fields = ['title', 'is_active']


class LocationFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    city = django_filters.CharFilter(lookup_expr='icontains')
    state = django_filters.CharFilter(lookup_expr='icontains')
    country = django_filters.CharFilter(lookup_expr='icontains')
    is_headquarters = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Location
        fields = ['name', 'city', 'is_headquarters', 'is_active']


class DocumentFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    document_type = django_filters.CharFilter()
    is_verified = django_filters.BooleanFilter()
    is_confidential = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Document
        fields = ['employee', 'document_type', 'is_verified', 'is_confidential']


class CertificationFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    is_verified = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    expiry_after = django_filters.DateFilter(field_name='expiry_date', lookup_expr='gte')
    expiry_before = django_filters.DateFilter(field_name='expiry_date', lookup_expr='lte')

    class Meta:
        model = Certification
        fields = ['employee', 'is_verified', 'is_active']


class EmployeeTransferFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    transfer_type = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])
    effective_after = django_filters.DateFilter(field_name='effective_date', lookup_expr='gte')
    effective_before = django_filters.DateFilter(field_name='effective_date', lookup_expr='lte')

    class Meta:
        model = EmployeeTransfer
        fields = ['employee', 'transfer_type', 'status']


class EmployeePromotionFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ])
    effective_after = django_filters.DateFilter(field_name='effective_date', lookup_expr='gte')

    class Meta:
        model = EmployeePromotion
        fields = ['employee', 'status']


class ResignationRequestFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('submitted', 'Submitted'), ('accepted', 'Accepted'),
        ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn'), ('completed', 'Completed'),
    ])
    primary_reason = django_filters.CharFilter()

    class Meta:
        model = ResignationRequest
        fields = ['employee', 'status', 'primary_reason']


class ExitInterviewFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    is_completed = django_filters.BooleanFilter()
    interview_date = django_filters.DateFilter()

    class Meta:
        model = ExitInterview
        fields = ['employee', 'is_completed']


class EmployeeSkillFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    skill = django_filters.UUIDFilter()
    proficiency = django_filters.CharFilter()
    is_verified = django_filters.BooleanFilter()

    class Meta:
        model = EmployeeSkill
        fields = ['employee', 'skill', 'proficiency', 'is_verified']


class EmployeeAddressFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    address_type = django_filters.CharFilter()
    is_primary = django_filters.BooleanFilter()

    class Meta:
        model = EmployeeAddress
        fields = ['employee', 'address_type', 'is_primary']


class EmployeeBankAccountFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    account_type = django_filters.CharFilter()
    is_primary = django_filters.BooleanFilter()

    class Meta:
        model = EmployeeBankAccount
        fields = ['employee', 'account_type', 'is_primary']


class EmergencyContactFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    is_primary = django_filters.BooleanFilter()

    class Meta:
        model = EmergencyContact
        fields = ['employee', 'is_primary']


class EmployeeDependentFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    relationship = django_filters.CharFilter()

    class Meta:
        model = EmployeeDependent
        fields = ['employee', 'relationship']


class EmploymentHistoryFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter()
    change_type = django_filters.CharFilter()
    effective_after = django_filters.DateFilter(field_name='effective_date', lookup_expr='gte')

    class Meta:
        model = EmploymentHistory
        fields = ['employee', 'change_type']


class SeparationChecklistFilter(django_filters.FilterSet):
    resignation = django_filters.UUIDFilter()
    assigned_to_department = django_filters.CharFilter()
    is_completed = django_filters.BooleanFilter()

    class Meta:
        model = SeparationChecklist
        fields = ['resignation', 'assigned_to_department', 'is_completed']
