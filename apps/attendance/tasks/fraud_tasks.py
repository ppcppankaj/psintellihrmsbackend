"""Fraud detection Celery tasks for attendance."""

from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from apps.core.celery_tasks import TenantAwareTask
from apps.attendance.models import AttendancePunch, AttendanceRecord, FraudLog
from apps.notifications.services import NotificationService


@shared_task(bind=True)
def evaluate_recent_punches(self, organization_id: str):
    """Review recent punches with high fraud scores and persist fraud logs."""

    organization = TenantAwareTask.get_organization(organization_id)
    cutoff = timezone.now() - timedelta(hours=12)
    suspicious_punches = AttendancePunch.objects.filter(
        organization=organization,
        fraud_score__gte=50,
        created_at__gte=cutoff
    ).select_related('employee', 'attendance')

    for punch in suspicious_punches:
        FraudLog.objects.get_or_create(
            organization=organization,
            employee=punch.employee,
            punch=punch,
            fraud_type='suspicious_pattern',
            defaults={
                'severity': 'high',
                'details': {
                    'fraud_score': float(punch.fraud_score or 0),
                    'punch_type': punch.punch_type,
                    'flags': punch.fraud_flags,
                }
            }
        )
        if punch.attendance and not punch.attendance.is_flagged:
            punch.attendance.is_flagged = True
            punch.attendance.save(update_fields=['is_flagged'])


@shared_task(bind=True)
def escalate_flagged_attendance(self, organization_id: str):
    """Notify HR about attendance records that remain flagged after review."""

    organization = TenantAwareTask.get_organization(organization_id)
    pending_records = AttendanceRecord.objects.filter(
        organization=organization,
        is_flagged=True,
        approved_by__isnull=True,
        date__lte=timezone.localdate()
    ).select_related('employee', 'employee__user')

    for record in pending_records:
        user = getattr(record.employee, 'user', None)
        if not user:
            continue
        NotificationService.notify(
            user=user,
            title='Attendance flagged for review',
            message=f'Attendance for {record.date} requires HR review due to high fraud score.',
            notification_type='warning',
            entity_type='attendance',
            entity_id=record.id
        )
*** End Patch