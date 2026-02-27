"""
Employee Serializers
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from apps.authentication.models import Branch
from apps.core.upload_validators import validate_upload as _validate_upload

from .models import (
    Employee, Department, Designation, Location,
    EmployeeAddress, EmployeeBankAccount, EmergencyContact,
    EmployeeDependent, Skill, EmployeeSkill,
    EmploymentHistory, Document, Certification,
    EmployeeTransfer, EmployeePromotion, ResignationRequest, ExitInterview,
    SeparationChecklist
)


class _OrgScopedValidatorMixin:
    """Shared helpers to validate that related objects belong to the request organization."""

    org_missing_error = 'Organization context missing in request.'

    def _get_request(self):
        return self.context.get('request')

    def _get_request_org(self):
        request = self._get_request()
        organization = getattr(request, 'organization', None) if request else None
        if not organization:
            raise serializers.ValidationError({'organization': self.org_missing_error})
        return organization

    def _validate_org_fk(self, value, label):
        if value is None:
            return value
        organization = self._get_request_org()
        if value.organization_id != organization.id:
            raise serializers.ValidationError(f"{label} does not belong to this organization.")
        return value

    def _restrict_queryset(self, model_cls):
        request = self._get_request()
        organization = getattr(request, 'organization', None) if request else None
        if organization is None:
            return model_cls.objects.none()
        return model_cls.objects.filter(organization=organization)


class TenantScopedSerializerMixin(_OrgScopedValidatorMixin):
    """Automatically inject organization context on create/update operations."""

    def create(self, validated_data):
        validated_data.setdefault('organization', self._get_request_org())
        return super().create(validated_data)

    def update(self, instance, validated_data):
        organization = self._get_request_org()
        if instance.organization_id != organization.id:
            raise serializers.ValidationError('Cannot operate on another organization\'s record.')
        return super().update(instance, validated_data)


class EmployeeRelationSerializerMixin(TenantScopedSerializerMixin):
    """Ensures referenced employee belongs to the active organization."""

    def validate_employee(self, employee):
        return self._validate_org_fk(employee, 'Employee')


# =========================
# SAFE SERIALIZERS (UNCHANGED)
# =========================

class DepartmentSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    head_name = serializers.CharField(source='head.full_name', read_only=True)

    class Meta:
        model = Department
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'parent', 'parent_name',
            'head', 'head_name', 'branch', 'cost_center', 'employee_count', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'employee_count', 'created_at', 'updated_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_employee_count(self, obj):
        if hasattr(obj, "employee_count"):
            return obj.employee_count
        return obj.employees.filter(is_active=True, is_deleted=False).count()


class DesignationSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = [
            'id', 'organization', 'name', 'code', 'description', 'level',
            'grade', 'job_family', 'min_salary', 'max_salary', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class LocationSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            'id', 'organization', 'name', 'code', 'address_line1', 'address_line2',
            'city', 'state', 'country', 'postal_code',
            'latitude', 'longitude', 'geo_fence_radius',
            'phone', 'email', 'timezone', 'is_headquarters', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class EmployeeListSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    first_name = serializers.ReadOnlyField(source='user.first_name')
    last_name = serializers.ReadOnlyField(source='user.last_name')
    email = serializers.ReadOnlyField()
    phone = serializers.ReadOnlyField(source='user.phone')
    department_name = serializers.CharField(source='department.name', read_only=True)
    designation_name = serializers.CharField(source='designation.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    manager_name = serializers.CharField(source='reporting_manager.full_name', read_only=True)
    avatar = serializers.ImageField(source='user.avatar', read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'full_name', 'first_name', 'last_name', 'email', 'phone', 'avatar',
            'department_name', 'designation_name', 'location_name',
            'manager_name', 'employment_type', 'employment_status',
            'date_of_joining', 'is_active'
        ]



class SkillSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            'id', 'organization', 'name', 'category', 'description',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

class EmployeeSkillSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    class Meta:
        model = EmployeeSkill
        fields = [
            'id', 'organization', 'employee', 'skill', 'proficiency', 'years_of_experience',
            'is_primary', 'is_verified', 'verified_by', 'skill_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'skill_name', 'created_at', 'updated_at']
    
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            request = self._get_request()
            organization = getattr(request, 'organization', None) if request else None
            if organization:
                self.fields['skill'].queryset = Skill.objects.filter(organization=organization)
                self.fields['verified_by'].queryset = Employee.objects.filter(organization=organization)

    def validate_skill(self, skill):
        return self._validate_org_fk(skill, 'Skill')

class EmployeeAddressSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = EmployeeAddress
        fields = [
            'id', 'organization', 'employee', 'address_type',
            'address_line1', 'address_line2', 'city', 'state', 'country', 'postal_code',
            'is_primary', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )

class EmployeeBankAccountSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = EmployeeBankAccount
        fields = [
            'id', 'organization', 'employee',
            'account_holder_name', 'bank_name', 'branch_name', 'account_number', 'ifsc_code',
            'account_type', 'is_primary', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )

class EmergencyContactSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = [
            'id', 'organization', 'employee',
            'name', 'relationship', 'phone', 'alternate_phone', 'email', 'address',
            'is_primary', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )

class EmployeeDependentSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = EmployeeDependent
        fields = [
            'id', 'organization', 'employee',
            'name', 'relationship', 'date_of_birth', 'gender',
            'is_covered_in_insurance', 'is_disabled',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )

class EmploymentHistorySerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    previous_department_name = serializers.CharField(source='previous_department.name', read_only=True)
    new_department_name = serializers.CharField(source='new_department.name', read_only=True)
    previous_designation_name = serializers.CharField(source='previous_designation.name', read_only=True)
    new_designation_name = serializers.CharField(source='new_designation.name', read_only=True)
    
    class Meta:
        model = EmploymentHistory
        fields = [
            'id', 'organization', 'employee', 'change_type', 'effective_date',
            'previous_department', 'previous_department_name',
            'previous_designation', 'previous_designation_name',
            'previous_location', 'previous_manager',
            'new_department', 'new_department_name',
            'new_designation', 'new_designation_name',
            'new_location', 'new_manager',
            'remarks', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self._get_request()
        organization = getattr(request, 'organization', None) if request else None
        if organization:
            dept_qs = Department.objects.filter(organization=organization)
            desig_qs = Designation.objects.filter(organization=organization)
            loc_qs = Location.objects.filter(organization=organization)
            mgr_qs = Employee.objects.filter(organization=organization)
            for field in ['previous_department', 'new_department']:
                self.fields[field].queryset = dept_qs
            for field in ['previous_designation', 'new_designation']:
                self.fields[field].queryset = desig_qs
            for field in ['previous_location', 'new_location']:
                self.fields[field].queryset = loc_qs
            for field in ['previous_manager', 'new_manager']:
                self.fields[field].queryset = mgr_qs

    def validate(self, attrs):
        for field in [
            'previous_department', 'new_department', 'previous_designation', 'new_designation',
            'previous_location', 'new_location', 'previous_manager', 'new_manager'
        ]:
            value = attrs.get(field)
            if value:
                self._validate_org_fk(value, field.replace('_', ' ').title())
        return super().validate(attrs)

class DocumentSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Document
        fields = [
            'id', 'organization', 'employee', 'document_type',
            'name', 'description', 'file', 'file_url', 'file_size', 'file_type',
            'is_verified', 'verified_by', 'verified_at',
            'expiry_date', 'is_confidential',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'file_size', 'file_type', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )
            self.fields['verified_by'].queryset = Employee.objects.filter(
                organization=request.organization
            )

    @extend_schema_field({'type': 'string', 'format': 'uri', 'nullable': True})
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class CertificationSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    is_expired = serializers.ReadOnlyField()
    certificate_file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Certification
        fields = [
            'id', 'organization', 'employee',
            'name', 'issuing_organization', 'credential_id', 'credential_url',
            'issue_date', 'expiry_date', 'is_expired',
            'is_verified', 'verified_by', 'verified_at',
            'certificate_file', 'certificate_file_url',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'is_verified', 'verified_by', 'verified_at', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['employee'].queryset = Employee.objects.filter(
                organization=request.organization
            )
            self.fields['verified_by'].queryset = Employee.objects.filter(
                organization=request.organization
            )

    @extend_schema_field({'type': 'string', 'format': 'uri', 'nullable': True})
    def get_certificate_file_url(self, obj):
        if obj.certificate_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.certificate_file.url)
            return obj.certificate_file.url
        return None

    def validate_verified_by(self, employee):
        if employee:
            return self._validate_org_fk(employee, 'Verifier')
        return employee


class EmployeeCreateSerializer(_OrgScopedValidatorMixin, serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    role_ids = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone = serializers.CharField(required=False, allow_blank=True)
    
    # Nested Write Fields
    skills = serializers.ListField(child=serializers.DictField(), required=False, write_only=True)
    bank_account = serializers.DictField(required=False, write_only=True)
    salary_structure = serializers.DictField(required=False, write_only=True)
    
    class Meta:
        model = Employee
        fields = [
            'employee_id', 'email', 'first_name', 'last_name', 'phone',
            'password', 'role_ids',
            'skills', 'bank_account', 'salary_structure',
            'department', 'designation', 'location', 'reporting_manager',
            'employment_type', 'date_of_joining', 'branch'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['department'].queryset = Department.objects.filter(organization=request.organization)
            self.fields['designation'].queryset = Designation.objects.filter(organization=request.organization)
            self.fields['location'].queryset = Location.objects.filter(organization=request.organization)
            self.fields['reporting_manager'].queryset = Employee.objects.filter(organization=request.organization)
            self.fields['branch'].queryset = Branch.objects.filter(organization=request.organization)

    def validate_department(self, value):
        return self._validate_org_fk(value, 'Department')

    def validate_designation(self, value):
        return self._validate_org_fk(value, 'Designation')

    def validate_location(self, value):
        return self._validate_org_fk(value, 'Location')

    def validate_branch(self, value):
        return self._validate_org_fk(value, 'Branch')

    def validate(self, attrs):
        required_fields = ['department', 'designation', 'location', 'branch', 'employment_type', 'date_of_joining']
        missing = [field for field in required_fields if not attrs.get(field)]
        if missing:
            raise serializers.ValidationError({field: 'This field is required.' for field in missing})
        return super().validate(attrs)

class EmployeeUpdateSerializer(_OrgScopedValidatorMixin, serializers.ModelSerializer):
    role_ids = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    
    # Nested Write Fields
    skills = serializers.ListField(child=serializers.DictField(), required=False, write_only=True)
    bank_account = serializers.DictField(required=False, write_only=True)
    salary_structure = serializers.DictField(required=False, write_only=True)
    
    class Meta:
        model = Employee
        fields = [
            'first_name', 'last_name', 'role_ids',
            'skills', 'bank_account', 'salary_structure',
            'department', 'designation', 'location', 'reporting_manager',
            'employment_type', 'employment_status', 'branch'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['department'].queryset = Department.objects.filter(organization=request.organization)
            self.fields['designation'].queryset = Designation.objects.filter(organization=request.organization)
            self.fields['location'].queryset = Location.objects.filter(organization=request.organization)
            self.fields['reporting_manager'].queryset = Employee.objects.filter(organization=request.organization)
            self.fields['branch'].queryset = Branch.objects.filter(organization=request.organization)

    def validate_department(self, value):
        return self._validate_org_fk(value, 'Department')

    def validate_designation(self, value):
        return self._validate_org_fk(value, 'Designation')

    def validate_location(self, value):
        return self._validate_org_fk(value, 'Location')

    def validate_branch(self, value):
        return self._validate_org_fk(value, 'Branch')

    def validate(self, attrs):
        for field in ['department', 'designation', 'location', 'branch']:
            if field in attrs and attrs[field] is None:
                raise serializers.ValidationError({field: 'This field cannot be null for company policy.'})
        return super().validate(attrs)

class EmployeeDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    first_name = serializers.ReadOnlyField(source='user.first_name')
    last_name = serializers.ReadOnlyField(source='user.last_name')
    email = serializers.ReadOnlyField()
    phone = serializers.ReadOnlyField(source='user.phone')
    department_name = serializers.CharField(source='department.name', read_only=True)
    designation_name = serializers.CharField(source='designation.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    manager_name = serializers.CharField(source='reporting_manager.full_name', read_only=True)
    avatar = serializers.ImageField(source='user.avatar', read_only=True)
    
    addresses = EmployeeAddressSerializer(many=True, read_only=True)
    bank_accounts = EmployeeBankAccountSerializer(many=True, read_only=True)
    skills = EmployeeSkillSerializer(many=True, read_only=True)
    dependents = EmployeeDependentSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id', 'full_name', 'first_name', 'last_name', 'email', 'phone', 'avatar',
            'department', 'department_name', 
            'designation', 'designation_name', 
            'location', 'location_name',
            'reporting_manager', 'manager_name', 
            'employment_type', 'employment_status', 'date_of_joining', 
            'gender', 'date_of_birth', 'marital_status', 'blood_group',
            'addresses', 'bank_accounts', 'skills', 'dependents', 'documents',
            'is_active', 'created_at', 'updated_at'
        ]

class OrgChartSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    name = serializers.ReadOnlyField(source='full_name')
    title = serializers.ReadOnlyField(source='designation.name')
    
    class Meta:
        model = Employee
        fields = ['id', 'name', 'title', 'avatar', 'children']
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_children(self, obj):
        if hasattr(obj, 'direct_reports'):
             return OrgChartSerializer(obj.direct_reports.filter(is_active=True), many=True).data
        return []

class EmployeeBulkImportSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[_validate_upload])

class DepartmentBulkImportSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[_validate_upload])

class DesignationBulkImportSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[_validate_upload])


# =========================
# 🔒 HARDENED SERIALIZERS
# =========================

class EmployeeTransferSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    from_department = serializers.PrimaryKeyRelatedField(source='department', queryset=Department.objects.none(), required=False, allow_null=True)
    from_department_name = serializers.CharField(source='department.name', read_only=True)
    to_department_name = serializers.CharField(source='to_department.name', read_only=True)
    from_location = serializers.PrimaryKeyRelatedField(source='location', queryset=Location.objects.none(), required=False, allow_null=True)
    from_location_name = serializers.CharField(source='location.name', read_only=True)
    to_location_name = serializers.CharField(source='to_location.name', read_only=True)
    from_manager = serializers.PrimaryKeyRelatedField(source='employee.reporting_manager', read_only=True)
    from_manager_name = serializers.CharField(source='employee.reporting_manager.full_name', read_only=True)
    to_manager_name = serializers.CharField(source='to_manager.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transfer_type_display = serializers.CharField(source='get_transfer_type_display', read_only=True)
    remarks = serializers.CharField(source='reason', required=False, allow_blank=True)

    class Meta:
        model = EmployeeTransfer
        fields = [
            'id',
            'organization',
            'employee',
            'employee_name',
            'transfer_type',
            'from_department',
            'from_department_name',
            'to_department',
            'to_department_name',
            'from_location',
            'from_location_name',
            'to_location',
            'to_location_name',
            'from_manager',
            'from_manager_name',
            'to_manager',
            'to_manager_name',
            'effective_date',
            'remarks',
            'status',
            'status_display',
            'transfer_type_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'organization',
            'employee_name',
            'from_department_name',
            'to_department_name',
            'from_location_name',
            'to_location_name',
            'from_manager',
            'from_manager_name',
            'to_manager_name',
            'status',
            'initiated_by',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        ]

    def validate_employee(self, employee):
        return super().validate_employee(employee)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self._get_request()
        organization = getattr(request, 'organization', None) if request else None
        if organization:
            dept_qs = Department.objects.filter(organization=organization)
            loc_qs = Location.objects.filter(organization=organization)
            mgr_qs = Employee.objects.filter(organization=organization)
            self.fields['from_department'].queryset = dept_qs
            self.fields['to_department'].queryset = dept_qs
            self.fields['from_location'].queryset = loc_qs
            self.fields['to_location'].queryset = loc_qs
            self.fields['to_manager'].queryset = mgr_qs

    def validate(self, attrs):
        for field in ['department', 'location', 'to_department', 'to_location', 'to_manager']:
            value = attrs.get(field)
            if value:
                self._validate_org_fk(value, field.replace('_', ' ').title())
        return super().validate(attrs)


class EmployeePromotionSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    from_designation_name = serializers.CharField(source='from_designation.name', read_only=True)
    to_designation_name = serializers.CharField(source='to_designation.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    remarks = serializers.CharField(source='reason', required=False, allow_blank=True)

    class Meta:
        model = EmployeePromotion
        fields = [
            'id', 'organization',
            'employee',
            'employee_name',
            'from_designation',
            'from_designation_name',
            'to_designation',
            'to_designation_name',
            'effective_date',
            'remarks',
            'status',
            'status_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'organization',
            'employee_name',
            'from_designation_name',
            'to_designation_name',
            'status',
            'recommended_by',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self._get_request()
        organization = getattr(request, 'organization', None) if request else None
        if organization:
            designation_qs = Designation.objects.filter(organization=organization)
            self.fields['from_designation'].queryset = designation_qs
            self.fields['to_designation'].queryset = designation_qs

    def validate(self, attrs):
        for field in ['from_designation', 'to_designation']:
            if attrs.get(field):
                self._validate_org_fk(attrs[field], field.replace('_', ' ').title())
        return super().validate(attrs)


class ResignationRequestSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    primary_reason_display = serializers.CharField(source='get_primary_reason_display', read_only=True)
    secondary_reason = serializers.CharField(source='detailed_reason', required=False, allow_blank=True)
    last_working_date = serializers.DateField(source='requested_last_working_date', required=False)
    remarks = serializers.CharField(source='detailed_reason', read_only=True)

    class Meta:
        model = ResignationRequest
        fields = [
            'id', 'organization',
            'employee',
            'employee_name',
            'resignation_date',
            'primary_reason',
            'secondary_reason',
            'requested_last_working_date',
            'approved_last_working_date',
            'notice_period_days',
            'notice_period_waived',
            'shortfall_recovery',
            'new_employer',
            'last_working_date',
            'remarks',
            'exit_checklist_complete',
            'fnf_processed',
            'status',
            'status_display',
            'primary_reason_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'organization',
            'employee_name',
            'remarks',
            'status',
            'accepted_by',
            'accepted_at',
            'exit_checklist_complete',
            'fnf_processed',
            'created_at',
            'updated_at',
        ]

    def validate_employee(self, employee):
        return super().validate_employee(employee)

    def validate(self, attrs):
        approved_date = attrs.get('approved_last_working_date')
        if approved_date:
            baseline = attrs.get('resignation_date') or attrs.get('requested_last_working_date')
            if not baseline and self.instance:
                baseline = self.instance.resignation_date or self.instance.requested_last_working_date
            if baseline and approved_date < baseline:
                raise serializers.ValidationError({'approved_last_working_date': 'Approved last working date cannot be before resignation/requested dates.'})
        return super().validate(attrs)


class ExitInterviewSerializer(EmployeeRelationSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    interviewer_name = serializers.CharField(source='interviewer.full_name', read_only=True)
    average_rating = serializers.ReadOnlyField()
    responses = serializers.JSONField(source='additional_feedback', required=False)

    class Meta:
        model = ExitInterview
        fields = [
            'id', 'organization',
            'employee',
            'employee_name',
            'interviewer',
            'interviewer_name',
            'responses',
            'average_rating',
            'is_completed',
            'completed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'organization',
            'employee_name',
            'interviewer_name',
            'average_rating',
            'is_completed',
            'completed_at',
            'created_at',
            'updated_at',
        ]

    def validate_interviewer(self, interviewer):
        if interviewer:
            return self._validate_org_fk(interviewer, 'Interviewer')
        return interviewer


class SeparationChecklistSerializer(TenantScopedSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='resignation.employee.full_name', read_only=True)

    class Meta:
        model = SeparationChecklist
        fields = [
            'id', 'organization', 'resignation', 'employee_name', 'task_name', 'description',
            'assigned_to_department', 'assigned_to', 'due_date', 'is_completed',
            'completed_by', 'completed_at', 'notes', 'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'employee_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self._get_request()
        organization = getattr(request, 'organization', None) if request else None
        if organization:
            self.fields['resignation'].queryset = ResignationRequest.objects.filter(organization=organization)
            employee_qs = Employee.objects.filter(organization=organization)
            self.fields['assigned_to'].queryset = employee_qs
            self.fields['completed_by'].queryset = employee_qs

    def validate_resignation(self, resignation):
        return self._validate_org_fk(resignation, 'Resignation')

    def validate_assigned_to(self, employee):
        if employee:
            return self._validate_org_fk(employee, 'Assignee')
        return employee

    def validate_completed_by(self, employee):
        if employee:
            return self._validate_org_fk(employee, 'Completer')
        return employee
