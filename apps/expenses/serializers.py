"""Expense Serializers"""

from rest_framework import serializers
from decimal import Decimal
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import (
    ExpenseCategory, ExpenseClaim, ExpenseItem, ExpenseApproval,
    EmployeeAdvance, AdvanceSettlement
)


class ExpenseCategorySerializer(serializers.ModelSerializer):
    """Serializer for expense categories"""
    
    class Meta:
        model = ExpenseCategory
        fields = [
            'id', 'name', 'code', 'description',
            'max_limit_per_claim', 'max_monthly_limit',
            'requires_receipt', 'requires_approval', 'min_amount_for_receipt',
            'gl_account', 'cost_center', 'designation_limits',
            'is_active', 'display_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExpenseItemSerializer(serializers.ModelSerializer):
    """Serializer for expense items"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = ExpenseItem
        fields = [
            'id', 'category', 'category_name',
            'expense_date', 'description',
            'claimed_amount', 'approved_amount',
            'receipt', 'receipt_number', 'vendor_name',
            'is_approved', 'rejection_reason',
            'currency', 'exchange_rate',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'approved_amount', 'is_approved', 'rejection_reason', 'created_at', 'updated_at']


class ExpenseApprovalSerializer(serializers.ModelSerializer):
    """Serializer for expense approvals"""
    approver_name = serializers.CharField(source='approver.full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = ExpenseApproval
        fields = [
            'id', 'approver', 'approver_name',
            'level', 'action', 'comments',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ExpenseClaimListSerializer(serializers.ModelSerializer):
    """List serializer for expense claims"""
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    item_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ExpenseClaim
        fields = [
            'id', 'claim_number', 'employee', 'employee_id', 'employee_name',
            'title', 'claim_date', 'expense_from', 'expense_to',
            'total_claimed_amount', 'total_approved_amount', 'total_paid_amount',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'item_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'claim_number', 'total_claimed_amount', 'total_approved_amount',
            'total_paid_amount', 'created_at', 'updated_at'
        ]
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_item_count(self, obj):
        return obj.items.count()


class ExpenseClaimDetailSerializer(ExpenseClaimListSerializer):
    """Detail serializer with nested items and approvals"""
    items = ExpenseItemSerializer(many=True, read_only=True)
    approvals = ExpenseApprovalSerializer(many=True, read_only=True)
    current_approver_name = serializers.CharField(
        source='current_approver.full_name', read_only=True, allow_null=True
    )
    approved_by_name = serializers.CharField(
        source='approved_by.full_name', read_only=True, allow_null=True
    )
    
    class Meta(ExpenseClaimListSerializer.Meta):
        fields = ExpenseClaimListSerializer.Meta.fields + [
            'description', 'items', 'approvals',
            'current_approver', 'current_approver_name',
            'approved_by', 'approved_by_name', 'approved_at',
            'rejection_reason', 'paid_by', 'paid_at',
            'payment_reference', 'payment_mode', 'advance_adjusted'
        ]


class CreateExpenseClaimSerializer(serializers.Serializer):
    """Serializer for creating expense claim with items"""
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    claim_date = serializers.DateField()
    expense_from = serializers.DateField()
    expense_to = serializers.DateField()
    items = ExpenseItemSerializer(many=True)
    
    def validate(self, data):
        if data['expense_from'] > data['expense_to']:
            raise serializers.ValidationError("expense_from cannot be after expense_to")
        if not data.get('items'):
            raise serializers.ValidationError("At least one expense item is required")
        return data


class ApproveExpenseSerializer(serializers.Serializer):
    """Serializer for approving/rejecting expenses"""
    action = serializers.ChoiceField(choices=['approve', 'reject', 'return'])
    comments = serializers.CharField(required=False, allow_blank=True)
    item_adjustments = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="List of {item_id, approved_amount, rejection_reason}"
    )


class ProcessPaymentSerializer(serializers.Serializer):
    """Serializer for processing expense payment"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_mode = serializers.ChoiceField(choices=['bank_transfer', 'cash', 'cheque', 'wallet'])
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    adjust_advance_id = serializers.UUIDField(required=False, allow_null=True)


class EmployeeAdvanceListSerializer(serializers.ModelSerializer):
    """List serializer for employee advances"""
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = EmployeeAdvance
        fields = [
            'id', 'advance_number', 'employee', 'employee_id', 'employee_name',
            'purpose', 'advance_date', 'amount',
            'settlement_type', 'amount_settled', 'remaining_balance',
            'status', 'status_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'advance_number', 'amount_settled', 'remaining_balance',
            'created_at', 'updated_at'
        ]


class EmployeeAdvanceDetailSerializer(EmployeeAdvanceListSerializer):
    """Detail serializer with settlements"""
    settlements = serializers.SerializerMethodField()
    approved_by_name = serializers.CharField(
    source='approved_by.full_name', read_only=True, allow_null=True
    )
    
    class Meta(EmployeeAdvanceListSerializer.Meta):
        fields = EmployeeAdvanceListSerializer.Meta.fields + [
            'deduction_start_month', 'monthly_deduction_amount',
            'approved_by', 'approved_by_name', 'approved_at',
            'rejection_reason', 'disbursed_at', 'disbursed_by',
            'disbursement_reference', 'disbursement_mode', 'settlements'
        ]
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_settlements(self, obj):
        settlements = obj.settlements.all()
        return AdvanceSettlementSerializer(settlements, many=True).data


class CreateAdvanceSerializer(serializers.Serializer):
    """Serializer for creating advance request"""
    purpose = serializers.CharField()
    advance_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1'))
    settlement_type = serializers.ChoiceField(choices=['expense', 'salary', 'mixed'])
    deduction_start_month = serializers.DateField(required=False, allow_null=True)
    monthly_deduction_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )


class ApproveAdvanceSerializer(serializers.Serializer):
    """Serializer for approving/rejecting advances"""
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    comments = serializers.CharField(required=False, allow_blank=True)


class DisburseAdvanceSerializer(serializers.Serializer):
    """Serializer for disbursing advance"""
    disbursement_mode = serializers.ChoiceField(choices=['bank_transfer', 'cash', 'cheque'])
    disbursement_reference = serializers.CharField(required=False, allow_blank=True)


class AdvanceSettlementSerializer(serializers.ModelSerializer):
    """Serializer for advance settlements"""
    settlement_type_display = serializers.CharField(source='get_settlement_type_display', read_only=True)
    expense_claim_number = serializers.CharField(
        source='expense_claim.claim_number', read_only=True, allow_null=True
    )
    
    class Meta:
        model = AdvanceSettlement
        fields = [
            'id', 'settlement_type', 'settlement_type_display',
            'amount', 'settlement_date',
            'expense_claim', 'expense_claim_number', 'payslip',
            'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class BulkApproveRejectSerializer(serializers.Serializer):
    """Serializer for bulk approve/reject actions"""
    claim_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        help_text="List of expense claim IDs to process"
    )
    comments = serializers.CharField(required=False, allow_blank=True)


class ExportReportSerializer(serializers.Serializer):
    """Serializer for export report parameters"""
    format = serializers.ChoiceField(choices=['csv', 'excel'], default='csv')
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    status = serializers.ChoiceField(
        choices=['all', 'draft', 'submitted', 'pending_approval', 'approved', 'rejected', 'paid', 'cancelled'],
        default='all',
        required=False
    )
    employee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Filter by specific employees"
    )
