"""Attendance recalculation tasks."""

from datetime import datetime
from celery import shared_task
from django.utils import timezone
from apps.core.celery_tasks import TenantAwareTask
from apps.attendance.models import AttendanceRecord


@shared_task(bind=True)
def recalculate_attendance(self, organization_id: str, attendance_date: str):
    """Recalculate attendance metrics for a specific date."""

    organization = TenantAwareTask.get_organization(organization_id)
    try:
        target_date = datetime.fromisoformat(attendance_date).date()
    except (TypeError, ValueError):
        target_date = timezone.localdate()

    records = AttendanceRecord.objects.filter(
        organization=organization,
        date=target_date
    )

    for record in records:
        if hasattr(record, 'recalculate'):
            record.recalculate()
*** End Patch