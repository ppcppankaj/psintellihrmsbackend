"""
Attendance Services - Geo-fence, Fraud Detection, Verification
"""

import math
from decimal import Decimal
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db.models import Sum, Q, Count


class GeoFenceService:
    """
    Geo-fence validation service.
    Validates if punch location is within allowed geo-fences.
    """
    
    # Earth radius in meters
    EARTH_RADIUS_M = 6371000
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula.
        Returns distance in meters.
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return GeoFenceService.EARTH_RADIUS_M * c
    
    @classmethod
    def validate_location(
        cls,
        employee,
        latitude: float,
        longitude: float,
        accuracy: float = None
    ) -> Dict:
        """
        Validate if employee location is within any allowed geo-fence.
        
        Returns:
            {
                'valid': bool,
                'geo_fence': GeoFence or None,
                'distance_meters': float,
                'message': str
            }
        """
        from apps.attendance.models import GeoFence
        
        # Get geo-fences for employee's location
        geo_fences = []
        
        # Primary geo-fence from employee's location
        if employee.location_id:
            geo_fences = list(GeoFence.objects.filter(
                location_id=employee.location_id,
                is_active=True
            ))
        
        if not geo_fences:
            # No geo-fences configured - allow punch
            return {
                'valid': True,
                'geo_fence': None,
                'distance_meters': 0,
                'message': 'No geo-fence configured - punch allowed'
            }
        
        # Check each geo-fence
        best_match = None
        min_distance = float('inf')
        
        for geo_fence in geo_fences:
            distance = cls.haversine_distance(
                latitude, longitude,
                float(geo_fence.latitude), float(geo_fence.longitude)
            )
            
            if distance < min_distance:
                min_distance = distance
                best_match = geo_fence
            
            # Check if within radius (considering accuracy)
            effective_radius = geo_fence.radius_meters
            if accuracy and accuracy > 0:
                effective_radius += accuracy  # Allow for GPS inaccuracy
            
            if distance <= effective_radius:
                return {
                    'valid': True,
                    'geo_fence': geo_fence,
                    'distance_meters': distance,
                    'message': f'Within geo-fence: {geo_fence.name}'
                }
        
        # Not within any geo-fence
        return {
            'valid': False,
            'geo_fence': best_match,
            'distance_meters': min_distance,
            'message': f'Outside geo-fence. Nearest: {best_match.name} ({min_distance:.0f}m away)'
        }


class FraudDetectionService:
    """
    Fraud detection service for attendance punches.
    Calculates fraud score based on multiple factors.
    """
    
    # Fraud score weights
    WEIGHTS = {
        'mock_gps': 30,
        'rooted_device': 20,
        'emulator': 25,
        'geo_mismatch': 15,
        'device_mismatch': 10,
        'vpn_detected': 10,
        'suspicious_timing': 10,
        'face_mismatch': 20,
        'liveness_failed': 25,
    }
    
    @classmethod
    def calculate_fraud_score(
        cls,
        employee,
        punch_data: Dict,
        previous_punches: List = None
    ) -> Tuple[Decimal, List[str]]:
        """
        Calculate fraud score for a punch.
        
        Returns:
            (fraud_score: Decimal, fraud_flags: List[str])
        """
        score = 0
        flags = []
        
        # Mock GPS detection
        if punch_data.get('is_mock_gps'):
            score += cls.WEIGHTS['mock_gps']
            flags.append('mock_gps')
        
        # Rooted/jailbroken device
        if punch_data.get('is_rooted'):
            score += cls.WEIGHTS['rooted_device']
            flags.append('rooted_device')
        
        # Emulator detection
        if punch_data.get('is_emulator'):
            score += cls.WEIGHTS['emulator']
            flags.append('emulator')
        
        # Device mismatch (using different device than usual)
        if punch_data.get('device_id'):
            if cls._is_device_mismatch(employee, punch_data['device_id']):
                score += cls.WEIGHTS['device_mismatch']
                flags.append('device_mismatch')
        
        # Geo-fence mismatch
        if punch_data.get('geo_valid') is False:
            score += cls.WEIGHTS['geo_mismatch']
            flags.append('geo_mismatch')
        
        # Suspicious timing patterns
        if previous_punches:
            if cls._has_suspicious_timing(previous_punches, punch_data.get('punch_time')):
                score += cls.WEIGHTS['suspicious_timing']
                flags.append('suspicious_timing')
        
        # Face verification failed
        if punch_data.get('face_verified') is False:
            score += cls.WEIGHTS['face_mismatch']
            flags.append('face_mismatch')
        
        # Liveness check failed
        if punch_data.get('liveness_verified') is False:
            score += cls.WEIGHTS['liveness_failed']
            flags.append('liveness_failed')
        
        # Normalize score to 0-100
        fraud_score = min(Decimal(score), Decimal(100))
        
        return fraud_score, flags
    
    @classmethod
    def _is_device_mismatch(cls, employee, device_id: str) -> bool:
        """Check if device is different from usual"""
        from apps.attendance.models import AttendancePunch
        
        # Get last 10 punches
        recent_devices = AttendancePunch.objects.filter(
            employee=employee,
            device_id__isnull=False
        ).exclude(
            device_id=''
        ).order_by('-punch_time')[:10].values_list('device_id', flat=True)
        
        if not recent_devices:
            return False  # No history, can't determine mismatch
        
        # If current device not in recent devices, it's a mismatch
        return device_id not in recent_devices
    
    @classmethod
    def _has_suspicious_timing(cls, previous_punches, current_time: datetime) -> bool:
        """Detect suspicious timing patterns"""
        if not previous_punches or not current_time:
            return False
        
        # Check for too-rapid punches (less than 5 minutes apart)
        for punch in previous_punches[:3]:
            time_diff = abs((current_time - punch.punch_time).total_seconds())
            if time_diff < 300:  # 5 minutes
                return True
        
        return False
    
    @classmethod
    def should_flag_for_review(cls, fraud_score: Decimal) -> bool:
        """Determine if punch should be flagged for review"""
        return fraud_score >= 50
    
    @classmethod
    def get_severity(cls, fraud_score: Decimal) -> str:
        """Get severity level based on fraud score"""
        if fraud_score >= 70:
            return 'critical'
        elif fraud_score >= 50:
            return 'high'
        elif fraud_score >= 30:
            return 'medium'
        return 'low'


class AttendanceService:
    """
    Core attendance service for punch operations.
    """
    
    @staticmethod
    def _build_failure(message: str, attendance=None, warnings=None) -> Dict:
        return {
            'success': False,
            'message': message,
            'attendance': attendance,
            'punch': None,
            'fraud_score': 0,
            'warnings': warnings or [],
        }

    @staticmethod
    def _validate_tenant(employee, organization) -> bool:
        return not organization or employee.organization_id == organization.id

    @classmethod
    def _validate_security_flags(cls, employee, punch_data: Dict):
        if punch_data.get('is_rooted'):
            return cls._build_failure('Rooted or jailbroken devices are not allowed.')
        if punch_data.get('is_emulator'):
            return cls._build_failure('Punch rejected because the device appears to be an emulator.')
        if punch_data.get('is_mock_gps'):
            return cls._build_failure('Mock GPS detected. Disable mock locations to continue.')

        device_id = punch_data.get('device_id')
        if device_id and cls._is_device_mismatch(employee, device_id):
            return cls._build_failure('Device mismatch detected. Please use the registered device to punch.')
        return None

    @staticmethod
    def _is_low_face_confidence(punch_data: Dict) -> bool:
        face_confidence = punch_data.get('face_confidence')
        if face_confidence is None:
            return False
        try:
            return Decimal(str(face_confidence)) < Decimal('0.80')
        except Exception:
            return False

    @classmethod
    def _create_fraud_logs(cls, employee, punch, events: List[Dict]):
        if not events:
            return
        from apps.attendance.models import FraudLog

        for event in events:
            FraudLog.objects.create(
                employee=employee,
                organization=punch.organization,
                punch=punch,
                fraud_type=event['type'],
                severity=event.get('severity', 'medium'),
                details=event.get('details', {})
            )

    @classmethod
    def _apply_shift_status(cls, attendance, shift, total_hours: Optional[Decimal] = None):
        from apps.attendance.models import AttendanceRecord
        if not shift:
            attendance.status = AttendanceRecord.STATUS_PRESENT
            return

        total_hours = total_hours if total_hours is not None else attendance.total_hours or Decimal('0')

        if total_hours < Decimal(str(shift.half_day_hours)):
            attendance.status = AttendanceRecord.STATUS_HALF_DAY
        elif attendance.late_minutes > 0:
            attendance.status = AttendanceRecord.STATUS_LATE
        elif attendance.early_out_minutes > 0:
            attendance.status = AttendanceRecord.STATUS_EARLY_OUT
        else:
            attendance.status = AttendanceRecord.STATUS_PRESENT

    @classmethod
    def _ensure_overtime_request(cls, attendance, total_hours: Decimal, shift):
        if not shift or total_hours is None:
            return
        if total_hours <= Decimal(str(shift.working_hours)):
            attendance.overtime_hours = None
            return

        requested_hours = (total_hours - Decimal(str(shift.working_hours))).quantize(Decimal('0.01'))
        attendance.overtime_hours = requested_hours

        from apps.attendance.models import OvertimeRequest

        OvertimeRequest.objects.update_or_create(
            attendance=attendance,
            defaults={
                'employee': attendance.employee,
                'branch': attendance.branch,
                'organization': attendance.organization,
                'requested_hours': requested_hours,
                'status': OvertimeRequest.STATUS_PENDING,
            }
        )
    @classmethod
    def punch_in(cls, employee, punch_data: Dict, organization=None) -> Dict:
        """
        Process punch-in request.
        
        Args:
            employee: Employee instance
            punch_data: {
                'latitude': float,
                'longitude': float,
                'accuracy': float,
                'device_id': str,
                'device_model': str,
                'is_rooted': bool,
                'is_emulator': bool,
                'is_mock_gps': bool,
                'selfie': file (optional),
            }
        
        Returns:
            {
                'success': bool,
                'message': str,
                'attendance': AttendanceRecord or None,
                'punch': AttendancePunch or None,
                'fraud_score': float,
                'warnings': list,
            }
        """
        from apps.attendance.models import AttendanceRecord, AttendancePunch

        organization = organization or employee.organization
        if not cls._validate_tenant(employee, organization):
            return cls._build_failure('Cross-tenant punch attempt blocked.')

        if not punch_data.get('face_verified', False):
            return cls._build_failure('Face verification failed. Please retry.')
        if not punch_data.get('liveness_verified', False):
            return cls._build_failure('Liveness detection failed. Punch rejected.')

        security_failure = cls._validate_security_flags(employee, punch_data)
        if security_failure:
            return security_failure

        today = timezone.localdate()
        warnings = []
        attendance, _ = AttendanceRecord.objects.get_or_create(
            employee=employee,
            date=today,
            defaults={
                'device_id': punch_data.get('device_id', ''),
                'organization': organization,
                'branch': employee.branch,
            }
        )

        if attendance.organization_id != organization.id:
            return cls._build_failure('Attendance record belongs to another tenant.', attendance)

        if attendance.check_in and not attendance.check_out:
            return cls._build_failure('Already punched in. Please punch out first.', attendance, ['Already punched in'])

        geo_result = GeoFenceService.validate_location(
            employee,
            punch_data.get('latitude'),
            punch_data.get('longitude'),
            punch_data.get('accuracy')
        )
        punch_data['geo_valid'] = geo_result['valid']
        if not geo_result['valid']:
            warnings.append(geo_result['message'])

        previous_punches = list(AttendancePunch.objects.filter(
            employee=employee
        ).order_by('-punch_time')[:5])

        fraud_score, fraud_flags = FraudDetectionService.calculate_fraud_score(
            employee, punch_data, previous_punches
        )
        fraud_events = []

        if not geo_result['valid']:
            fraud_score += Decimal('40')
            fraud_flags.append('geo_mismatch')
            fraud_events.append({
                'type': 'geo_mismatch',
                'severity': 'high',
                'details': {
                    'message': geo_result['message'],
                    'distance_meters': geo_result.get('distance_meters'),
                }
            })

        low_face_confidence = cls._is_low_face_confidence(punch_data)
        if low_face_confidence:
            fraud_score += Decimal('30')
            fraud_flags.append('low_face_confidence')
            fraud_events.append({
                'type': 'face_mismatch',
                'severity': 'medium',
                'details': {'face_confidence': float(punch_data.get('face_confidence') or 0)}
            })

        punch_time = timezone.now()
        punch = AttendancePunch.objects.create(
            employee=employee,
            organization=organization,
            branch=employee.branch,
            attendance=attendance,
            punch_type=AttendancePunch.PUNCH_IN,
            punch_time=punch_time,
            latitude=punch_data.get('latitude'),
            longitude=punch_data.get('longitude'),
            accuracy=punch_data.get('accuracy'),
            geo_fence=geo_result.get('geo_fence'),
            device_id=punch_data.get('device_id', ''),
            device_model=punch_data.get('device_model', ''),
            is_rooted=punch_data.get('is_rooted', False),
            is_emulator=punch_data.get('is_emulator', False),
            is_mock_gps=punch_data.get('is_mock_gps', False),
            face_verified=punch_data.get('face_verified', False),
            face_confidence=punch_data.get('face_confidence'),
            liveness_verified=punch_data.get('liveness_verified', False),
            fraud_score=fraud_score,
            fraud_flags=fraud_flags,
            is_flagged=low_face_confidence,
            selfie=punch_data.get('selfie'),
        )

        shift = cls._get_employee_shift(employee)

        attendance.check_in = punch_time
        attendance.check_in_latitude = punch_data.get('latitude')
        attendance.check_in_longitude = punch_data.get('longitude')
        attendance.check_in_fraud_score = fraud_score
        attendance.device_id = punch_data.get('device_id', '')
        attendance.branch = attendance.branch or employee.branch

        if shift:
            late_minutes = cls._calculate_late_minutes(punch_time, shift)
            attendance.late_minutes = late_minutes
            if late_minutes > 0:
                warnings.append(f'Late by {late_minutes} minutes')
        cls._apply_shift_status(attendance, shift)

        logged_types = {event['type'] for event in fraud_events}
        if FraudDetectionService.should_flag_for_review(fraud_score):
            attendance.is_flagged = True
            warnings.append('Flagged for review due to potential fraud indicators')
            punch.is_flagged = True
            punch.save(update_fields=['is_flagged'])
            severity = FraudDetectionService.get_severity(fraud_score)
            for flag in fraud_flags:
                if flag in logged_types:
                    continue
                fraud_events.append({
                    'type': flag,
                    'severity': severity,
                    'details': {
                        'fraud_score': float(fraud_score),
                        'device_id': punch.device_id,
                    }
                })
                logged_types.add(flag)

        cls._create_fraud_logs(employee, punch, fraud_events)
        attendance.save()

        return {
            'success': True,
            'message': 'Punch in successful',
            'attendance': attendance,
            'punch': punch,
            'fraud_score': float(fraud_score),
            'warnings': warnings,
        }
    
    @classmethod
    def punch_out(cls, employee, punch_data: Dict, organization=None) -> Dict:
        """Process punch-out request"""
        from apps.attendance.models import AttendanceRecord, AttendancePunch

        organization = organization or employee.organization
        if not cls._validate_tenant(employee, organization):
            return cls._build_failure('Cross-tenant punch blocked.')

        if not punch_data.get('face_verified', False):
            return cls._build_failure('Face verification failed. Please retry after capturing a clear selfie.')
        if not punch_data.get('liveness_verified', False):
            return cls._build_failure('Liveness verification failed. Punch rejected.')

        security_failure = cls._validate_security_flags(employee, punch_data)
        if security_failure:
            return security_failure

        today = timezone.localdate()
        warnings = []

        try:
            attendance = AttendanceRecord.objects.get(employee=employee, date=today)
        except AttendanceRecord.DoesNotExist:
            return cls._build_failure('No punch-in found for today. Please punch in first.', warnings=['No punch-in record'])

        if attendance.organization_id != organization.id:
            return cls._build_failure('Attendance record belongs to another tenant.', attendance)

        if not attendance.check_in:
            return cls._build_failure('No punch-in found. Please punch in first.', attendance, ['No punch-in record'])

        if attendance.check_out:
            return cls._build_failure('Already punched out for today.', attendance, ['Already punched out'])

        geo_result = GeoFenceService.validate_location(
            employee,
            punch_data.get('latitude'),
            punch_data.get('longitude'),
            punch_data.get('accuracy')
        )
        punch_data['geo_valid'] = geo_result['valid']
        if not geo_result['valid']:
            warnings.append(geo_result['message'])

        previous_punches = list(AttendancePunch.objects.filter(
            employee=employee
        ).order_by('-punch_time')[:5])

        fraud_score, fraud_flags = FraudDetectionService.calculate_fraud_score(
            employee, punch_data, previous_punches
        )
        fraud_events = []

        if not geo_result['valid']:
            fraud_score += Decimal('40')
            fraud_flags.append('geo_mismatch')
            fraud_events.append({
                'type': 'geo_mismatch',
                'severity': 'high',
                'details': {
                    'message': geo_result['message'],
                    'distance_meters': geo_result.get('distance_meters'),
                }
            })

        low_face_confidence = cls._is_low_face_confidence(punch_data)
        if low_face_confidence:
            fraud_score += Decimal('30')
            fraud_flags.append('low_face_confidence')
            fraud_events.append({
                'type': 'face_mismatch',
                'severity': 'medium',
                'details': {'face_confidence': float(punch_data.get('face_confidence') or 0)}
            })

        punch_time = timezone.now()
        punch = AttendancePunch.objects.create(
            employee=employee,
            organization=organization,
            branch=attendance.branch or employee.branch,
            attendance=attendance,
            punch_type=AttendancePunch.PUNCH_OUT,
            punch_time=punch_time,
            latitude=punch_data.get('latitude'),
            longitude=punch_data.get('longitude'),
            accuracy=punch_data.get('accuracy'),
            geo_fence=geo_result.get('geo_fence'),
            device_id=punch_data.get('device_id', ''),
            device_model=punch_data.get('device_model', ''),
            is_rooted=punch_data.get('is_rooted', False),
            is_emulator=punch_data.get('is_emulator', False),
            is_mock_gps=punch_data.get('is_mock_gps', False),
            face_verified=punch_data.get('face_verified', False),
            face_confidence=punch_data.get('face_confidence'),
            liveness_verified=punch_data.get('liveness_verified', False),
            fraud_score=fraud_score,
            fraud_flags=fraud_flags,
            is_flagged=low_face_confidence,
            selfie=punch_data.get('selfie'),
        )

        attendance.check_out = punch_time
        attendance.check_out_latitude = punch_data.get('latitude')
        attendance.check_out_longitude = punch_data.get('longitude')
        attendance.check_out_fraud_score = fraud_score

        total_seconds = (attendance.check_out - attendance.check_in).total_seconds()
        total_hours = (Decimal(total_seconds) / Decimal('3600')).quantize(Decimal('0.01'))
        attendance.total_hours = total_hours

        shift = cls._get_employee_shift(employee)
        if shift:
            early_out_mins = cls._calculate_early_out_minutes(punch_time, shift)
            attendance.early_out_minutes = early_out_mins
            if early_out_mins > 0:
                warnings.append(f'Early out by {early_out_mins} minutes')
        cls._apply_shift_status(attendance, shift, total_hours)
        if shift and attendance.status == AttendanceRecord.STATUS_HALF_DAY:
            warnings.append('Marked as half day due to insufficient hours')
        cls._ensure_overtime_request(attendance, total_hours, shift)

        logged_types = {event['type'] for event in fraud_events}
        if FraudDetectionService.should_flag_for_review(fraud_score):
            attendance.is_flagged = True
            punch.is_flagged = True
            punch.save(update_fields=['is_flagged'])
            severity = FraudDetectionService.get_severity(fraud_score)
            for flag in fraud_flags:
                if flag in logged_types:
                    continue
                fraud_events.append({
                    'type': flag,
                    'severity': severity,
                    'details': {
                        'fraud_score': float(fraud_score),
                        'device_id': punch.device_id,
                    }
                })
                logged_types.add(flag)

        cls._create_fraud_logs(employee, punch, fraud_events)
        attendance.save()

        return {
            'success': True,
            'message': 'Punch out successful',
            'attendance': attendance,
            'punch': punch,
            'fraud_score': float(fraud_score),
            'warnings': warnings,
        }
    
    @classmethod
    def _get_employee_shift(cls, employee, target_date=None):
        """
        Get employee's assigned shift for a specific date.
        
        Lookup order:
        1. Active ShiftAssignment for employee on target date
        2. Department default shift (if configured)
        3. Organization default shift ('GEN')
        
        Args:
            employee: Employee instance
            target_date: Date to get shift for (defaults to today)
        
        Returns:
            Shift instance or None
        """
        from apps.attendance.models import Shift, ShiftAssignment
        
        if target_date is None:
            target_date = timezone.localdate()
        
        # 1. Check for employee-specific shift assignment
        shift_assignment = ShiftAssignment.objects.filter(
            employee=employee,
            effective_from__lte=target_date,
            is_active=True
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=target_date)
        ).select_related('shift').order_by('-effective_from').first()
        
        if shift_assignment and shift_assignment.shift.is_active:
            return shift_assignment.shift
        
        # 2. Fallback to department default shift (if configured)
        if employee.department_id and hasattr(employee.department, 'default_shift_id'):
            dept_shift = Shift.objects.filter(
                id=employee.department.default_shift_id,
                is_active=True
            ).first()
            if dept_shift:
                return dept_shift
        
        # 3. Fallback to organization default 'GEN' shift
        return Shift.objects.filter(
            code='GEN',
            organization=employee.organization,
            is_active=True
        ).first()
    
    @classmethod
    def _calculate_late_minutes(cls, punch_time: datetime, shift) -> int:
        """Calculate late minutes based on shift"""
        if not shift:
            return 0
        
        # Get shift start time for today
        shift_start = datetime.combine(punch_time.date(), shift.start_time)
        shift_start = timezone.make_aware(shift_start)
        
        # Add grace period
        grace_end = shift_start + timedelta(minutes=shift.grace_in_minutes)
        
        if punch_time > grace_end:
            late_seconds = (punch_time - grace_end).total_seconds()
            return int(late_seconds // 60)
        
        return 0
    
    @classmethod
    def _calculate_early_out_minutes(cls, punch_time: datetime, shift) -> int:
        """Calculate early out minutes"""
        if not shift:
            return 0
        
        shift_end = datetime.combine(punch_time.date(), shift.end_time)
        shift_end = timezone.make_aware(shift_end)
        
        # Subtract grace period
        grace_start = shift_end - timedelta(minutes=shift.grace_out_minutes)
        
        if punch_time < grace_start:
            early_seconds = (grace_start - punch_time).total_seconds()
            return int(early_seconds // 60)
        
        return 0

    @classmethod
    def get_monthly_summary(cls, organization, employee_id, month: int, year: int) -> Optional[Dict]:
        """Aggregate attendance metrics for payroll consumption."""
        from datetime import date
        from apps.attendance.models import AttendanceRecord
        from apps.employees.models import Employee

        employee = Employee.objects.filter(id=employee_id, organization=organization).first()
        if not employee:
            return None

        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        records = AttendanceRecord.objects.filter(
            organization=organization,
            employee=employee,
            date__gte=start_date,
            date__lte=end_date
        )

        aggregates = records.aggregate(
            present_days=Count('id', filter=Q(status=AttendanceRecord.STATUS_PRESENT)),
            half_days=Count('id', filter=Q(status=AttendanceRecord.STATUS_HALF_DAY)),
            late_days=Count('id', filter=Q(status=AttendanceRecord.STATUS_LATE)),
            overtime_hours=Sum('overtime_hours'),
        )

        return {
            'employee_id': str(employee.id),
            'month': month,
            'year': year,
            'present_days': aggregates['present_days'] or 0,
            'half_days': aggregates['half_days'] or 0,
            'late_days': aggregates['late_days'] or 0,
            'overtime_hours': (aggregates['overtime_hours'] or Decimal('0')).quantize(Decimal('0.01')),
        }


class ShiftManagementService:
    """
    Service for managing shift assignments and schedules.
    Supports fixed shifts, rotating shifts, and bulk operations.
    """
    
    @classmethod
    def assign_shifts_to_employees(
        cls,
        employee_ids: List,
        shift_id: int,
        effective_from,
        effective_to=None,
        created_by=None
    ) -> Dict:
        """
        Bulk assign shifts to multiple employees.
        
        Args:
            employee_ids: List of employee IDs
            shift_id: Shift to assign
            effective_from: Start date
            effective_to: End date (None = ongoing)
            created_by: Employee who created the assignment
        
        Returns:
            {
                'success': bool,
                'created_count': int,
                'errors': list,
                'assignments': list
            }
        """
        from apps.attendance.models import Shift, ShiftAssignment
        from apps.employees.models import Employee
        
        created_count = 0
        errors = []
        assignments = []
        
        # Validate shift exists
        try:
            shift = Shift.objects.get(id=shift_id, is_active=True)
        except Shift.DoesNotExist:
            return {
                'success': False,
                'created_count': 0,
                'errors': ['Shift not found or inactive'],
                'assignments': []
            }
        
        for emp_id in employee_ids:
            try:
                employee = Employee.objects.get(id=emp_id)
                
                # Check for overlapping assignments
                overlapping = ShiftAssignment.objects.filter(
                    employee=employee,
                    effective_from__lte=effective_to if effective_to else effective_from,
                    is_active=True
                ).filter(
                    Q(effective_to__isnull=True) | Q(effective_to__gte=effective_from)
                ).exists()
                
                if overlapping:
                    errors.append(f'Employee {employee.employee_id} has overlapping shift assignment')
                    continue
                
                # Create assignment
                assignment = ShiftAssignment.objects.create(
                    employee=employee,
                    shift=shift,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    is_primary=True,
                    organization=employee.organization,
                    branch=employee.branch,
                    created_by=created_by
                )
                assignments.append(assignment)
                created_count += 1
                
            except Employee.DoesNotExist:
                errors.append(f'Employee ID {emp_id} not found')
            except Exception as e:
                errors.append(f'Error assigning shift to {emp_id}: {str(e)}')
        
        return {
            'success': created_count > 0,
            'created_count': created_count,
            'errors': errors,
            'assignments': assignments
        }
    
    @classmethod
    def get_rotating_shift_schedule(
        cls,
        employee,
        start_date,
        end_date
    ) -> List[Dict]:
        """
        Get shift schedule for an employee within a date range.
        Useful for rotating shifts or schedule previews.
        
        Args:
            employee: Employee instance
            start_date: Start date
            end_date: End date
        
        Returns:
            List of {'date': date, 'shift': Shift, 'shift_name': str}
        """
        from datetime import timedelta
        
        schedule = []
        current_date = start_date
        
        while current_date <= end_date:
            shift = AttendanceService._get_employee_shift(employee, current_date)
            schedule.append({
                'date': current_date,
                'shift': shift,
                'shift_name': shift.name if shift else 'No Shift Assigned'
            })
            current_date += timedelta(days=1)
        
        return schedule
    
    @classmethod
    def end_shift_assignment(cls, assignment_id, effective_to, ended_by=None):
        """
        End an existing shift assignment.
        
        Args:
            assignment_id: ShiftAssignment ID
            effective_to: End date
            ended_by: Employee who ended the assignment
        
        Returns:
            {'success': bool, 'message': str}
        """
        from apps.attendance.models import ShiftAssignment
        
        try:
            assignment = ShiftAssignment.objects.get(id=assignment_id)
            assignment.effective_to = effective_to
            assignment.updated_by = ended_by
            assignment.save()
            
            return {
                'success': True,
                'message': f'Shift assignment ended on {effective_to}'
            }
        except ShiftAssignment.DoesNotExist:
            return {
                'success': False,
                'message': 'Shift assignment not found'
            }
