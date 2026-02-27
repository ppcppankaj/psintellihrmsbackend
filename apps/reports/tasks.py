"""Report tasks"""
from celery import shared_task
from .models import ReportExecution
from .services import ReportExecutionService


@shared_task
def run_report_execution(execution_id: str):
    execution = ReportExecution.objects.filter(id=execution_id).first()
    if not execution:
        return None
    user = execution.requested_by
    return ReportExecutionService.run_execution(execution, user)
