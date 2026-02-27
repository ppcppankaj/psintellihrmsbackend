"""
Leave Celery Tasks - Scheduled accrual and notifications
"""

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone


@shared_task
def run_monthly_accrual():
    """
    Run monthly leave accrual for all organizations.
    Scheduled to run on 1st of each month.
    """
    from apps.leave.services import LeaveBalanceService
    from apps.core.models import Organization
    from apps.core.context import set_current_organization
    
    organizations = Organization.objects.filter(is_active=True)
    
    for org in organizations:
        set_current_organization(org)
        try:
            LeaveBalanceService.run_monthly_accrual(org)
        except Exception as e:
            # Log error but continue with other organizations
            print(f"Accrual failed for {org.name}: {e}")
    
    set_current_organization(None)
    return f"Accrual completed for {organizations.count()} organizations"


@shared_task
def run_year_end_carryforward():
    """
    Run year-end carry forward for all organizations.
    Scheduled to run on January 1st.
    """
    from apps.leave.services import LeaveBalanceService
    from apps.core.models import Organization
    from apps.core.context import set_current_organization
    
    current_year = timezone.now().year
    previous_year = current_year - 1
    
    organizations = Organization.objects.filter(is_active=True)
    
    for org in organizations:
        set_current_organization(org)
        try:
            LeaveBalanceService.run_year_end_carryforward(previous_year, current_year, org)
        except Exception as e:
            print(f"Carry forward failed for {org.name}: {e}")
            
    set_current_organization(None)
    return f"Carry forward completed for {organizations.count()} organizations"


@shared_task
def send_leave_reminder():
    """
    Send reminder to approvers for pending leave requests.
    Runs daily.
    """
    from apps.leave.models import LeaveRequest
    from apps.core.models import Organization
    from apps.core.context import set_current_organization
    from datetime import timedelta
    
    cutoff = timezone.now() - timedelta(days=2)  # Pending for 2+ days
    
    organizations = Organization.objects.filter(is_active=True)
    
    for org in organizations:
        set_current_organization(org)
        pending = LeaveRequest.objects.filter(
            status=LeaveRequest.STATUS_PENDING,
            created_at__lt=cutoff,
            current_approver__isnull=False,
            organization=org
        ).select_related('current_approver', 'employee')
        
        for leave in pending:
            # Send notification to approver
            from apps.notifications.services import NotificationService
            
            if leave.current_approver:
                NotificationService.notify(
                    user=leave.current_approver.user,
                    title='Leave Request Pending Approval',
                    message=f'Leave request from {leave.employee} for {leave.start_date} to {leave.end_date} is pending your approval',
                    notification_type='warning',
                    entity_type='leave_request',
                    entity_id=leave.id
                )
            
    set_current_organization(None)
    return "Reminders sent"


@shared_task
def process_leave_escalation():
    """
    Escalate pending leave requests after timeout.
    Runs daily.
    """
    from apps.leave.models import LeaveRequest
    from apps.leave.services import LeaveApprovalService
    from apps.core.models import Organization
    from apps.core.context import set_current_organization
    from datetime import timedelta
    
    # Escalate if pending for more than 3 days
    escalation_cutoff = timezone.now() - timedelta(days=3)
    
    organizations = Organization.objects.filter(is_active=True)
    
    for org in organizations:
        set_current_organization(org)
        pending = LeaveRequest.objects.filter(
            status=LeaveRequest.STATUS_PENDING,
            created_at__lt=escalation_cutoff,
            current_approver__isnull=False,
            organization=org
        )
        
        for leave in pending:
            # Get next level approver
            current_level = leave.approvals.count() + 1
            next_approver = LeaveApprovalService.get_approver(
                leave.employee, level=current_level + 1
            )
            
            if next_approver:
                leave.current_approver = next_approver
                leave.save()
                
                # Send escalation notification
                from apps.notifications.services import NotificationService
                NotificationService.notify(
                    user=next_approver.user,
                    title='Leave Request Escalated',
                    message=f'Leave request from {leave.employee} has been escalated to you for approval',
                    notification_type='warning',
                    entity_type='leave_request',
                    entity_id=leave.id
                )
                
    set_current_organization(None)
    return "Escalations processed"


@shared_task
def send_leave_status_email(leave_request_id, status = None):
    """Send an email update to employees after leave approval/rejection."""
    from django.conf import settings
    from apps.leave.models import LeaveRequest

    leave_request = LeaveRequest.objects.select_related('employee__user').filter(id=leave_request_id).first()
    if not leave_request or not leave_request.employee or not leave_request.employee.user.email:
        return 'No recipient'

    resolved_status = status or leave_request.status
    employee_user = leave_request.employee.user
    subject = f"Leave {resolved_status.title()}"
    message = (
        f"Hi {employee_user.full_name},\n\n"
        f"Your leave request from {leave_request.start_date} to {leave_request.end_date} "
        f"has been {resolved_status}."
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    send_mail(subject, message, from_email, [employee_user.email], fail_silently=True)
    return f"leave-email:{leave_request_id}:{resolved_status}"


@shared_task
def expire_comp_off_leaves():
    """Automatically expire approved comp-off credits past their validity."""
    from apps.leave.models import CompensatoryLeave
    from apps.core.models import Organization
    from apps.core.context import set_current_organization

    today = timezone.now().date()
    organizations = Organization.objects.filter(is_active=True)
    expired_total = 0

    for org in organizations:
        set_current_organization(org)
        updated = CompensatoryLeave.objects.filter(
            organization=org,
            status__in=[
                CompensatoryLeave.STATUS_PENDING,
                CompensatoryLeave.STATUS_APPROVED,
            ],
            expiry_date__lt=today
        ).update(status=CompensatoryLeave.STATUS_EXPIRED)
        expired_total += updated

    set_current_organization(None)
    return f"Expired {expired_total} comp-off records"
