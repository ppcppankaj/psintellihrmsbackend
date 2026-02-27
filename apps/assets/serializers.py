"""
Asset Management Serializers
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import AssetCategory, Asset, AssetAssignment, AssetMaintenance, AssetRequest
from apps.employees.models import Employee


class AssetCategorySerializer(serializers.ModelSerializer):
    """Serializer for asset categories"""
    asset_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AssetCategory
        fields = ['id', 'name', 'code', 'description', 'icon', 'asset_count']
        read_only_fields = ['id']
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_asset_count(self, obj):
        return obj.assets.count()


class AssetListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for asset lists"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    assignee_name = serializers.CharField(source='current_assignee.full_name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Asset
        fields = [
            'id', 'name', 'asset_tag', 'serial_number', 'category', 'category_name',
            'status', 'status_display', 'current_assignee', 'assignee_name', 
            'location', 'purchase_date', 'warranty_expires'
        ]


class AssetDetailSerializer(serializers.ModelSerializer):
    """Detailed asset serializer with full info"""
    category = AssetCategorySerializer(read_only=True)
    category_id = serializers.UUIDField(write_only=True, source='category.id')
    assignee_name = serializers.CharField(source='current_assignee.full_name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assignments = serializers.SerializerMethodField()
    
    class Meta:
        model = Asset
        fields = [
            'id', 'name', 'asset_tag', 'serial_number', 'description',
            'category', 'category_id', 'status', 'status_display',
            'purchase_date', 'purchase_price', 'vendor', 'warranty_expires',
            'current_assignee', 'assignee_name', 'location', 'notes',
            'assignments', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'current_assignee', 'created_at', 'updated_at']
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_assignments(self, obj):
        recent = obj.assignments.select_related('employee')[:5]
        return AssetAssignmentSerializer(recent, many=True).data


class AssetSerializer(serializers.ModelSerializer):
    """Standard asset serializer for create/update"""
    
    class Meta:
        model = Asset
        fields = [
            'id', 'name', 'asset_tag', 'serial_number', 'description',
            'category', 'status', 'purchase_date', 'purchase_price', 
            'vendor', 'warranty_expires', 'location', 'notes'
        ]
        read_only_fields = ['id']


class AssetBulkImportSerializer(serializers.ModelSerializer):
    """Bulk import serializer for Assets with FK resolution"""
    category_code = serializers.CharField(write_only=True, required=False)
    assignee_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Asset
        fields = [
            'name', 'asset_tag', 'serial_number', 'description',
            'category_code', 'status', 'purchase_date',
            'purchase_price', 'vendor', 'warranty_expires',
            'location', 'notes', 'assignee_id'
        ]

    def validate(self, attrs):
        category_code = attrs.pop('category_code', None)
        if category_code:
            try:
                attrs['category'] = AssetCategory.objects.get(code=category_code)
            except AssetCategory.DoesNotExist:
                raise serializers.ValidationError({'category_code': f"Category with code '{category_code}' not found."})
        
        assignee_id = attrs.pop('assignee_id', None)
        if assignee_id:
            try:
                attrs['current_assignee'] = Employee.objects.get(employee_id=assignee_id)
                # If simplified assignment logic is needed without history, this is fine for bulk init.
                # If history is needed, we'd need post_save signals or explicit creation.
                # For now, matching model field direct assignment.
            except Employee.DoesNotExist:
                raise serializers.ValidationError({'assignee_id': f"Employee with ID '{assignee_id}' not found."})
        
        return attrs


class AssetAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for asset assignments"""
    asset_name = serializers.CharField(source='asset.name', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.full_name', read_only=True, allow_null=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = AssetAssignment
        fields = [
            'id', 'asset', 'asset_name', 'asset_tag', 'employee', 'employee_name',
            'assigned_date', 'assigned_by', 'assigned_by_name', 'notes',
            'returned_date', 'return_notes', 'is_active'
        ]
        read_only_fields = ['id', 'assigned_date', 'assigned_by']


class AssignAssetSerializer(serializers.Serializer):
    """Serializer for assigning an asset to an employee"""
    employee_id = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True)


class UnassignAssetSerializer(serializers.Serializer):
    """Serializer for returning an asset"""
    notes = serializers.CharField(required=False, allow_blank=True)


class AssetMaintenanceSerializer(serializers.ModelSerializer):
    """Serializer for asset maintenance records"""
    asset_name = serializers.CharField(source='asset.name', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    type_display = serializers.CharField(source='get_maintenance_type_display', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = AssetMaintenance
        fields = [
            'id', 'asset', 'asset_name', 'asset_tag',
            'maintenance_type', 'type_display', 'status', 'status_display',
            'title', 'description', 'scheduled_date', 'completed_date',
            'cost', 'vendor', 'performed_by', 'performed_by_name', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AssetRequestSerializer(serializers.ModelSerializer):
    """Serializer for asset requests"""
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True, allow_null=True)
    fulfilled_asset_tag = serializers.CharField(source='fulfilled_asset.asset_tag', read_only=True, allow_null=True)
    
    class Meta:
        model = AssetRequest
        fields = [
            'id', 'employee', 'employee_name', 'category', 'category_name',
            'title', 'description', 'justification', 'status', 'status_display',
            'requested_date', 'needed_by', 'reviewed_by', 'reviewed_by_name',
            'reviewed_at', 'review_notes', 'fulfilled_asset', 'fulfilled_asset_tag',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'requested_date', 'reviewed_by', 'reviewed_at', 'fulfilled_asset', 'created_at', 'updated_at']


class AssetRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating asset requests (employee self-service)"""
    
    class Meta:
        model = AssetRequest
        fields = ['category', 'title', 'description', 'justification', 'needed_by']


class AssetRequestReviewSerializer(serializers.Serializer):
    """Serializer for approving/rejecting asset requests"""
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    notes = serializers.CharField(required=False, allow_blank=True)


class AssetRequestFulfillSerializer(serializers.Serializer):
    """Serializer for fulfilling asset requests"""
    asset_id = serializers.UUIDField()


class DepreciationCalculationSerializer(serializers.Serializer):
    """Serializer for depreciation calculation response"""
    asset_id = serializers.UUIDField()
    asset_name = serializers.CharField()
    purchase_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    purchase_date = serializers.DateField()
    current_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    depreciation_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    depreciation_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    years_owned = serializers.DecimalField(max_digits=5, decimal_places=2)
    method = serializers.CharField()
