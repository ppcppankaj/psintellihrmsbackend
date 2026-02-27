"""
Attendance Serializers
"""

from rest_framework import serializers
from django.utils import timezone
from apps.core.upload_validators import validate_upload as _validate_upload
from .models import (
    Shift, GeoFence, AttendanceRecord,
    AttendancePunch, FraudLog, FaceEmbedding,
    ShiftAssignment, OvertimeRequest
)
from apps.employees.models import Location


class TenantScopedSerializer(serializers.ModelSerializer):
    """Base serializer enforcing tenant-safe related objects."""

    tenant_fields = tuple()

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
            raise serializers.ValidationError({field_name: 'Cross-tenant reference blocked.'})


class ShiftSerializer(TenantScopedSerializer):
    """Shift serializer"""
    tenant_fields = ('branch',)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = Shift
        fields = [
            'id', 'name', 'code', 'start_time', 'end_time', 'branch', 'branch_name',
            'grace_in_minutes', 'grace_out_minutes',
            'break_duration_minutes', 'working_hours', 'half_day_hours',
            'overtime_allowed', 'max_overtime_hours', 'is_night_shift',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class GeoFenceSerializer(TenantScopedSerializer):
    """Geo-fence serializer"""

    tenant_fields = ('location', 'branch')
    
    location_name = serializers.CharField(source='location.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = GeoFence
        fields = [
            'id', 'name', 'location', 'location_name', 'branch', 'branch_name',
            'latitude', 'longitude', 'radius_meters',
            'is_primary', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class GeoFenceBulkImportSerializer(serializers.ModelSerializer):
    """Bulk import serializer for GeoFence with location resolution"""
    location_code = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = GeoFence
        fields = [
            'name', 'location_code',
            'latitude', 'longitude', 'radius_meters',
            'is_primary', 'is_active'
        ]

    def validate(self, attrs):
        location_code = attrs.pop('location_code', None)
        request = self.context.get('request')
        organization = getattr(request, 'organization', None) if request else None
        if location_code:
            try:
                # Resolve location by code
                location = Location.objects.get(code=location_code)
                if organization and getattr(location, 'organization_id', None) != organization.id:
                    raise serializers.ValidationError({'location_code': 'Location belongs to another organization.'})
                attrs['location'] = location
            except Location.DoesNotExist:
                raise serializers.ValidationError({'location_code': f"Location with code '{location_code}' not found."})
        return attrs





class AttendancePunchSerializer(serializers.ModelSerializer):
    """Individual punch serializer"""
    
    class Meta:
        model = AttendancePunch
        fields = [
            'id', 'punch_type', 'punch_time',
            'latitude', 'longitude', 'accuracy',
            'face_verified', 'face_confidence', 'liveness_verified',
            'fraud_score', 'fraud_flags', 'is_flagged', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AttendanceRecordListSerializer(serializers.ModelSerializer):
    """Attendance record list serializer"""
    
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.user.full_name', read_only=True)
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee', 'employee_id', 'employee_name', 'date',
            'check_in', 'check_out', 'status', 'total_hours',
            'overtime_hours', 'late_minutes', 'early_out_minutes',
            'is_flagged', 'is_regularized'
        ]


class AttendanceRecordDetailSerializer(serializers.ModelSerializer):
    """Attendance record detail serializer"""
    
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.user.full_name', read_only=True)
    punches = AttendancePunchSerializer(many=True, read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.user.full_name', read_only=True)
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee', 'employee_id', 'employee_name', 'date',
            'check_in', 'check_out', 'status', 'total_hours',
            'overtime_hours', 'late_minutes', 'early_out_minutes',
            'check_in_latitude', 'check_in_longitude',
            'check_out_latitude', 'check_out_longitude',
            'check_in_fraud_score', 'check_out_fraud_score',
            'is_flagged', 'is_regularized', 'regularization_reason',
            'approved_by', 'approved_by_name', 'device_id',
            'punches', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PunchInSerializer(serializers.Serializer):
    """Punch-in request serializer"""
    
    latitude = serializers.DecimalField(max_digits=10, decimal_places=8, required=True)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=8, required=True)
    accuracy = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    device_model = serializers.CharField(max_length=100, required=False, allow_blank=True)
    
    is_rooted = serializers.BooleanField(required=False, default=False)
    is_emulator = serializers.BooleanField(required=False, default=False)
    is_mock_gps = serializers.BooleanField(required=False, default=False)

    face_verified = serializers.BooleanField(required=True)
    liveness_verified = serializers.BooleanField(required=True)
    face_confidence = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=1,
        required=False,
        allow_null=True
    )
    
    selfie = serializers.ImageField(required=False, allow_null=True, validators=[_validate_upload])


class PunchOutSerializer(PunchInSerializer):
    """Punch-out request serializer (same as punch-in)"""
    pass


class PunchResponseSerializer(serializers.Serializer):
    """Punch response serializer"""
    
    success = serializers.BooleanField()
    message = serializers.CharField()
    fraud_score = serializers.FloatField()
    warnings = serializers.ListField(child=serializers.CharField())
    attendance = AttendanceRecordDetailSerializer(required=False, allow_null=True)


class AttendanceRegularizationSerializer(serializers.Serializer):
    """Attendance regularization request"""
    
    date = serializers.DateField()
    check_in = serializers.DateTimeField(required=False, allow_null=True)
    check_out = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=500)
    
    def validate(self, data):
        if not data.get('check_in') and not data.get('check_out'):
            raise serializers.ValidationError("At least one of check_in or check_out is required")
        return data


class FraudLogSerializer(TenantScopedSerializer):
    """Fraud log serializer"""
    tenant_fields = ('employee', 'reviewed_by')
    
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.user.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.user.full_name', read_only=True)
    
    class Meta:
        model = FraudLog
        fields = [
            'id', 'employee', 'employee_id', 'employee_name', 'punch',
            'fraud_type', 'severity', 'details',
            'action_taken', 'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AttendanceSummarySerializer(serializers.Serializer):
    """Attendance summary for dashboard"""
    
    total_days = serializers.IntegerField()
    present_days = serializers.IntegerField()
    absent_days = serializers.IntegerField()
    late_days = serializers.IntegerField()
    half_days = serializers.IntegerField()
    leave_days = serializers.IntegerField()
    wfh_days = serializers.IntegerField()
    total_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    overtime_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_hours_per_day = serializers.DecimalField(max_digits=5, decimal_places=2)


class TeamAttendanceSerializer(serializers.Serializer):
    """Team attendance status"""
    
    employee_id = serializers.CharField()
    employee_name = serializers.CharField()
    avatar = serializers.URLField(allow_null=True)
    status = serializers.CharField()
    check_in = serializers.DateTimeField(allow_null=True)
    check_out = serializers.DateTimeField(allow_null=True)


class ShiftAssignmentSerializer(TenantScopedSerializer):
    """Shift assignment serializer"""
    tenant_fields = ('employee', 'shift', 'branch')
    
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.user.full_name', read_only=True)
    shift_name = serializers.CharField(source='shift.name', read_only=True)
    shift_code = serializers.CharField(source='shift.code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = ShiftAssignment
        fields = [
            'id', 'employee', 'employee_id', 'employee_name',
            'shift', 'shift_name', 'shift_code',
            'branch', 'branch_name', 'effective_from', 'effective_to',
            'is_primary', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        effective_from = attrs.get('effective_from') or (self.instance.effective_from if self.instance else None)
        effective_to = attrs.get('effective_to') if 'effective_to' in attrs else (self.instance.effective_to if self.instance else None)
        if effective_from and effective_to and effective_to < effective_from:
            raise serializers.ValidationError({'effective_to': 'Must be on or after effective_from.'})
        return attrs


class ShiftAssignmentBulkSerializer(serializers.Serializer):
    """Bulk assign shifts to multiple employees"""
    
    employee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1
    )
    shift = serializers.PrimaryKeyRelatedField(queryset=Shift.objects.none())
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(default=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'organization'):
            self.fields['shift'].queryset = Shift.objects.filter(
                organization=request.organization,
                is_active=True
            )
        else:
            self.fields['shift'].queryset = Shift.objects.none()


class OvertimeRequestSerializer(TenantScopedSerializer):
    """Overtime request serializer"""
    tenant_fields = ('employee', 'attendance', 'branch', 'reviewed_by')
    
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    employee_name = serializers.CharField(source='employee.user.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.user.full_name', read_only=True)
    attendance_date = serializers.DateField(source='attendance.date', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = OvertimeRequest
        fields = [
            'id', 'attendance', 'attendance_date',
            'employee', 'employee_id', 'employee_name',
            'branch', 'branch_name', 'requested_hours', 'approved_hours',
            'reason', 'status', 'reviewed_by', 'reviewed_by_name',
            'reviewed_at', 'review_notes', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'reviewed_by', 'reviewed_at', 'approved_hours', 'created_at']


class OvertimeApprovalSerializer(serializers.Serializer):
    """Overtime approval request"""
    
    approved_hours = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


class MonthlyReportSerializer(serializers.Serializer):
    """Monthly attendance report data"""
    
    employee_id = serializers.CharField()
    employee_name = serializers.CharField()
    department = serializers.CharField(allow_null=True)
    total_days = serializers.IntegerField()
    present_days = serializers.IntegerField()
    absent_days = serializers.IntegerField()
    late_days = serializers.IntegerField()
    half_days = serializers.IntegerField()
    leave_days = serializers.IntegerField()
    wfh_days = serializers.IntegerField()
    total_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    overtime_hours = serializers.DecimalField(max_digits=10, decimal_places=2)


class AnnualReportSerializer(serializers.Serializer):
    """Annual attendance report data"""
    
    employee_id = serializers.CharField()
    employee_name = serializers.CharField()
    department = serializers.CharField(allow_null=True)
    months = serializers.ListField(child=serializers.DictField())


class PayrollMonthlySummarySerializer(serializers.Serializer):
    """Payroll-facing monthly attendance summary."""

    employee_id = serializers.CharField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    year = serializers.IntegerField(min_value=2000)
    present_days = serializers.IntegerField(min_value=0)
    half_days = serializers.IntegerField(min_value=0)
    late_days = serializers.IntegerField(min_value=0)
    overtime_hours = serializers.DecimalField(max_digits=7, decimal_places=2)
