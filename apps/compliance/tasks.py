"""Compliance background tasks"""
from celery import shared_task
from .models import AuditExportRequest, RetentionExecution
from .services import AuditExportService, RetentionService


@shared_task
def run_audit_export(export_id: str):
    export_request = AuditExportRequest.objects.filter(id=export_id).first()
    if not export_request:
        return None
    user = export_request.requested_by
    return AuditExportService.run_export(export_request, user)


@shared_task
def run_retention_execution(execution_id: str):
    execution = RetentionExecution.objects.filter(id=execution_id).first()
    if not execution:
        return None
    return RetentionService.run_execution(execution, execution.requested_by)
