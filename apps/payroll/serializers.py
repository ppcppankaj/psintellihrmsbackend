from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import (
    EmployeeSalary, PayrollRun, Payslip, TaxDeclaration, ReimbursementClaim,
    EmployeeLoan, LoanRepayment
)
from apps.employees.serializers import EmployeeListSerializer


# ---------------------------------------------------------------------------
# Tenant-safe base serializer (cross-tenant FK guard)
# ---------------------------------------------------------------------------

class TenantScopedSerializer(serializers.ModelSerializer):
    """Base serializer that blocks cross-tenant FK writes."""

    tenant_fields = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        organization = self._get_organization()
        if not organization:
            return attrs
        for field_name in self.tenant_fields:
            value = attrs.get(field_name)
            if value is None and self.instance is not None:
                value = getattr(self.instance, field_name, None)
            self._assert_same_org(value, organization, field_name)
        return attrs

    def _get_organization(self):
        request = self.context.get('request') if hasattr(self, 'context') else None
        return getattr(request, 'organization', None)

    @staticmethod
    def _assert_same_org(value, organization, field_name):
        if not value or not organization:
            return
        related_org_id = getattr(value, 'organization_id', None)
        if related_org_id is None:
            return
        if related_org_id != organization.id:
            raise serializers.ValidationError(
                {field_name: 'Cross-tenant reference blocked.'}
            )


class EmployeeSalarySerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_name = serializers.ReadOnlyField(source='employee.user.full_name')

    class Meta:
        model = EmployeeSalary
        fields = [
            'id', 'organization', 'employee', 'employee_name',
            'effective_from', 'effective_to', 'is_active',
            'basic', 'hra', 'da', 'special_allowance', 'conveyance', 'medical_allowance', 'lta',
            'other_allowances', 'performance_bonus', 'variable_pay', 'arrears',
            'pf_employee', 'esi_employee', 'professional_tax', 'tds', 'other_deductions',
            'pf_employer', 'esi_employer', 'gratuity',
            'annual_ctc', 'monthly_gross', 'total_deductions', 'net_salary',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'annual_ctc', 'monthly_gross', 'total_deductions', 'net_salary', 'created_at', 'updated_at']


class PayrollRunSerializer(TenantScopedSerializer):
    tenant_fields = ('branch',)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'branch', 'branch_name', 'month', 'year', 'status', 'status_display',
            'pay_date', 'total_employees', 'total_gross', 'total_deductions',
            'total_net', 'processed_at', 'approved_at', 'locked_at', 'paid_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']


class PayslipListSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.full_name')
    employee_id = serializers.ReadOnlyField(source='employee.employee_id')
    month = serializers.ReadOnlyField(source='payroll_run.month')
    year = serializers.ReadOnlyField(source='payroll_run.year')

    class Meta:
        model = Payslip
        fields = [
            'id', 'employee', 'employee_name', 'employee_id', 
            'month', 'year', 'net_salary', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class PayslipSerializer(TenantScopedSerializer):
    tenant_fields = ('employee', 'payroll_run')
    employee_details = EmployeeListSerializer(source='employee', read_only=True)
    payroll_run_details = PayrollRunSerializer(source='payroll_run', read_only=True)

    class Meta:
        model = Payslip
        fields = [
            'id', 'employee', 'payroll_run', 'employee_details', 'payroll_run_details',
            'gross_salary', 'total_deductions', 'net_salary', 
            'earnings_breakdown', 'deductions_breakdown', 'pdf_file', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class TaxDeclarationSerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_name = serializers.ReadOnlyField(source='employee.user.full_name')

    class Meta:
        model = TaxDeclaration
        fields = [
            'id', 'employee', 'employee_name', 'financial_year', 'tax_regime',
            'declarations', 'proofs_submitted', 'proofs_verified',
            'total_exemptions', 'taxable_income', 'annual_tax', 'monthly_tds',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ReimbursementClaimListSerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_name = serializers.ReadOnlyField(source='employee.user.full_name')
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ReimbursementClaim
        fields = [
            'id', 'employee', 'employee_name', 'title', 'amount', 
            'status', 'status_display', 'submitted_at', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'submitted_at', 'created_at']


class ReimbursementClaimSerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_details = EmployeeListSerializer(source='employee', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ReimbursementClaim
        fields = [
            'id', 'organization', 'employee', 'employee_details',
            'title', 'amount', 'description', 'bill',
            'status', 'status_display', 'submitted_at', 'approved_at', 'paid_at',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'status', 'submitted_at', 'approved_at', 'paid_at', 'created_at', 'updated_at']


class SalaryRevisionSerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_name = serializers.ReadOnlyField(source='employee.user.full_name')
    revision_type = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeSalary
        fields = [
            'id', 'employee', 'employee_name', 'effective_from', 'effective_to',
            'is_active', 'basic', 'hra', 'da', 'special_allowance', 'conveyance',
            'medical_allowance', 'lta', 'other_allowances', 'pf_employee', 'esi_employee',
            'professional_tax', 'annual_ctc', 'monthly_gross', 'net_salary',
            'revision_type', 'created_at'
        ]

    @extend_schema_field({'type': 'string', 'enum': ['initial', 'increment', 'decrement', 'restructure']})
    def get_revision_type(self, obj):
        previous = EmployeeSalary.objects.filter(
            employee=obj.employee,
            effective_from__lt=obj.effective_from
        ).order_by('-effective_from').first()
        if not previous:
            return 'initial'
        if obj.annual_ctc > previous.annual_ctc:
            return 'increment'
        elif obj.annual_ctc < previous.annual_ctc:
            return 'decrement'
        return 'restructure'


class EmployeeLoanListSerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_name = serializers.ReadOnlyField(source='employee.user.full_name')
    employee_id = serializers.ReadOnlyField(source='employee.employee_id')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    loan_type_display = serializers.CharField(source='get_loan_type_display', read_only=True)

    class Meta:
        model = EmployeeLoan
        fields = [
            'id', 'employee', 'employee_name', 'employee_id', 'loan_type',
            'loan_type_display', 'principal_amount', 'emi_amount', 'outstanding_balance',
            'status', 'status_display', 'applied_at'
        ]


class EmployeeLoanSerializer(TenantScopedSerializer):
    tenant_fields = ('employee',)
    employee_details = EmployeeListSerializer(source='employee', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    loan_type_display = serializers.CharField(source='get_loan_type_display', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.user.full_name', read_only=True)

    class Meta:
        model = EmployeeLoan
        fields = [
            'id', 'organization', 'employee', 'employee_details',
            'loan_type', 'loan_type_display', 'principal_amount', 'interest_rate', 'tenure_months',
            'emi_amount', 'total_repayable', 'amount_repaid', 'outstanding_balance',
            'status', 'status_display', 'reason',
            'applied_at', 'approved_at', 'disbursed_at', 'closed_at', 'approved_by', 'approved_by_name',
            'deduct_from_salary', 'start_deduction_month', 'start_deduction_year',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'organization', 'status', 'emi_amount', 'total_repayable', 'amount_repaid',
            'outstanding_balance', 'applied_at', 'approved_at', 'disbursed_at',
            'closed_at', 'approved_by', 'created_at', 'updated_at'
        ]


class LoanRepaymentSerializer(TenantScopedSerializer):
    tenant_fields = ('loan',)
    loan_employee_name = serializers.CharField(source='loan.employee.user.full_name', read_only=True)

    class Meta:
        model = LoanRepayment
        fields = [
            'id', 'organization', 'loan', 'loan_employee_name', 'amount', 'repayment_date',
            'payslip', 'remarks', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
