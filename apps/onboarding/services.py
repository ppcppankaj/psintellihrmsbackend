"""Onboarding Services - Business Logic"""

from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from .models import (
    OnboardingTemplate, OnboardingTaskTemplate,
    EmployeeOnboarding, OnboardingTaskProgress, OnboardingDocument
)


class OnboardingService:
    """Service class for onboarding operations"""
    
    @staticmethod
    def find_template_for_employee(employee):
        """
        Find the most appropriate onboarding template for an employee.
        Priority: Department+Designation > Department > Designation > Default
        """
        # Try exact match: department + designation
        template = OnboardingTemplate.objects.filter(
            organization=employee.organization,
            department=employee.department,
            designation=employee.designation,
            is_active=True
        ).first()
        
        if template:
            return template
        
        # Try department only
        template = OnboardingTemplate.objects.filter(
            organization=employee.organization,
            department=employee.department,
            designation__isnull=True,
            is_active=True
        ).first()
        
        if template:
            return template
        
        # Try designation only
        template = OnboardingTemplate.objects.filter(
            organization=employee.organization,
            department__isnull=True,
            designation=employee.designation,
            is_active=True
        ).first()
        
        if template:
            return template
        
        # Fall back to default
        return OnboardingTemplate.objects.filter(
            organization=employee.organization,
            is_default=True,
            is_active=True
        ).first()
    
    @staticmethod
    @transaction.atomic
    def initiate_onboarding(employee, template=None, joining_date=None, 
                            hr_responsible=None, buddy=None):
        """
        Initiate onboarding for an employee.
        Creates EmployeeOnboarding and all task progress records.
        """
        # Find template if not provided
        if template is None:
            template = OnboardingService.find_template_for_employee(employee)
        
        if template is None:
            raise ValueError("No onboarding template found for employee")
        
        # Use employee's date_of_joining if not provided
        if joining_date is None:
            joining_date = employee.date_of_joining
        
        if joining_date is None:
            raise ValueError("Joining date is required")
        
        # Calculate dates
        start_date = joining_date - timedelta(days=template.days_before_joining)
        target_completion_date = joining_date + timedelta(days=template.days_to_complete)
        
        # Create onboarding instance
        onboarding = EmployeeOnboarding.objects.create(
            employee=employee,
            template=template,
            joining_date=joining_date,
            start_date=start_date,
            target_completion_date=target_completion_date,
            status=EmployeeOnboarding.STATUS_IN_PROGRESS,
            hr_responsible=hr_responsible,
            buddy=buddy
        )
        
        # Create task progress records from template
        task_templates = template.tasks.all().order_by('stage', 'order', 'due_days_offset')
        
        for task_template in task_templates:
            # Calculate due date based on offset from joining date
            due_date = joining_date + timedelta(days=task_template.due_days_offset)
            
            # Determine assignee
            assigned_to = OnboardingService._resolve_assignee(
                employee, task_template, hr_responsible
            )
            
            OnboardingTaskProgress.objects.create(
                onboarding=onboarding,
                task_template=task_template,
                title=task_template.title,
                description=task_template.description,
                stage=task_template.stage,
                is_mandatory=task_template.is_mandatory,
                assigned_to=assigned_to,
                due_date=due_date,
                status=OnboardingTaskProgress.STATUS_PENDING
            )
        
        # Update progress
        onboarding.update_progress()
        
        return onboarding
    
    @staticmethod
    def _resolve_assignee(employee, task_template, hr_responsible=None):
        """Resolve the assignee for a task based on task template settings"""
        assignee_type = task_template.assigned_to_type
        
        if assignee_type == OnboardingTaskTemplate.ASSIGNEE_EMPLOYEE:
            return employee
        elif assignee_type == OnboardingTaskTemplate.ASSIGNEE_MANAGER:
            return employee.reporting_manager
        elif assignee_type == OnboardingTaskTemplate.ASSIGNEE_HR:
            return hr_responsible
        # For IT, Admin, Finance - need to implement role-based lookup
        # For now, return HR responsible as fallback
        return hr_responsible
    
    @staticmethod
    @transaction.atomic
    def complete_task(task_progress, completed_by, notes='', attachment=None, acknowledged=False):
        """Mark an onboarding task as completed"""
        now = timezone.now()
        
        task_progress.status = OnboardingTaskProgress.STATUS_COMPLETED
        task_progress.completed_at = now
        task_progress.completed_by = completed_by
        task_progress.notes = notes
        task_progress.acknowledged = acknowledged
        
        if attachment:
            task_progress.attachment = attachment
        
        task_progress.save()
        
        # Update onboarding progress
        task_progress.onboarding.update_progress()
        
        # Check if all mandatory tasks are completed
        OnboardingService._check_completion(task_progress.onboarding)
        
        return task_progress
    
    @staticmethod
    def _check_completion(onboarding):
        """Check if onboarding is complete and update status"""
        pending_mandatory = onboarding.task_progress.filter(
            is_mandatory=True,
            status__in=[
                OnboardingTaskProgress.STATUS_PENDING,
                OnboardingTaskProgress.STATUS_IN_PROGRESS,
                OnboardingTaskProgress.STATUS_OVERDUE
            ]
        ).exists()
        
        if not pending_mandatory:
            onboarding.status = EmployeeOnboarding.STATUS_COMPLETED
            onboarding.actual_completion_date = timezone.now().date()
            onboarding.save(update_fields=['status', 'actual_completion_date'])
    
    @staticmethod
    def skip_task(task_progress, skipped_by, reason=''):
        """Skip a non-mandatory task"""
        if task_progress.is_mandatory:
            raise ValueError("Cannot skip mandatory tasks")
        
        task_progress.status = OnboardingTaskProgress.STATUS_SKIPPED
        task_progress.completed_by = skipped_by
        task_progress.notes = reason
        task_progress.save()
        
        task_progress.onboarding.update_progress()
        
        return task_progress
    
    @staticmethod
    @transaction.atomic
    def verify_document(document, verified_by, action='verify', rejection_reason=''):
        """Verify or reject an onboarding document"""
        now = timezone.now()
        
        if action == 'verify':
            document.status = OnboardingDocument.STATUS_VERIFIED
            document.verified_by = verified_by
            document.verified_at = now
        elif action == 'reject':
            document.status = OnboardingDocument.STATUS_REJECTED
            document.rejection_reason = rejection_reason
        
        document.save()
        return document
    
    @staticmethod
    def get_onboarding_summary(onboarding):
        """Get summary statistics for an onboarding"""
        tasks = onboarding.task_progress.all()
        documents = onboarding.documents.all()
        
        task_stats = {
            'total': tasks.count(),
            'completed': tasks.filter(status='completed').count(),
            'pending': tasks.filter(status='pending').count(),
            'overdue': tasks.filter(status='overdue').count(),
            'skipped': tasks.filter(status='skipped').count(),
        }
        
        doc_stats = {
            'total': documents.count(),
            'verified': documents.filter(status='verified').count(),
            'pending': documents.filter(status__in=['pending', 'uploaded']).count(),
            'rejected': documents.filter(status='rejected').count(),
        }
        
        # Group tasks by stage
        stages = {}
        for stage_code, stage_name in OnboardingTaskProgress._meta.get_field('stage').choices:
            stage_tasks = tasks.filter(stage=stage_code)
            stages[stage_code] = {
                'name': stage_name,
                'total': stage_tasks.count(),
                'completed': stage_tasks.filter(status='completed').count(),
            }
        
        return {
            'tasks': task_stats,
            'documents': doc_stats,
            'stages': stages,
            'progress_percentage': onboarding.progress_percentage,
            'days_remaining': (onboarding.target_completion_date - timezone.now().date()).days
        }
    
    @staticmethod
    def get_pending_tasks_for_user(user_employee):
        """Get all onboarding tasks assigned to a user"""
        return OnboardingTaskProgress.objects.filter(
            assigned_to=user_employee,
            status__in=['pending', 'in_progress', 'overdue']
        ).select_related('onboarding', 'onboarding__employee').order_by('due_date')
    
    @staticmethod
    def update_overdue_tasks():
        """Batch update to mark overdue tasks (to be run as scheduled task)"""
        today = timezone.now().date()
        
        updated = OnboardingTaskProgress.objects.filter(
            status__in=['pending', 'in_progress'],
            due_date__lt=today
        ).update(status=OnboardingTaskProgress.STATUS_OVERDUE)
        
        return updated
