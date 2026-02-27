"""
Leave Services - Accrual Engine, Sandwich Rules, Balance Management
"""

from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q


class LeaveCalculationService:
    """
    Calculate leave days considering:
    - Half days
    - Sandwich rules
    - Holidays
    - Weekends
    """
    
    @classmethod
    def calculate_leave_days(
        cls,
        start_date: date,
        end_date: date,
        start_day_type: str = 'full',
        end_day_type: str = 'full',
        leave_policy = None,
        employee = None,
    ) -> Tuple[Decimal, List[date]]:
        """
        Calculate total leave days and return dates.
        
        Args:
            start_date: Leave start date
            end_date: Leave end date
            start_day_type: 'full', 'first_half', 'second_half'
            end_day_type: 'full', 'first_half', 'second_half'
            leave_policy: LeavePolicy instance
            employee: Employee instance (for location-specific holidays)
        
        Returns:
            (total_days, list_of_dates)
        """
        if start_date > end_date:
            return Decimal('0'), []
        
        total_days = Decimal('0')
        leave_dates = []
        
        # Get holidays for the date range
        holidays = cls._get_holidays(start_date, end_date, employee)
        
        current_date = start_date
        while current_date <= end_date:
            is_weekend = current_date.weekday() >= 5
            is_holiday = current_date in holidays
            
            # Determine if this day counts
            should_count = True
            
            if leave_policy:
                # Check sandwich rule
                if not leave_policy.count_weekends and is_weekend:
                    should_count = leave_policy.sandwich_rule and cls._is_sandwiched(
                        current_date, start_date, end_date
                    )
                
                if not leave_policy.count_holidays and is_holiday:
                    should_count = leave_policy.sandwich_rule and cls._is_sandwiched(
                        current_date, start_date, end_date
                    )
            else:
                # Default: don't count weekends and holidays
                if is_weekend or is_holiday:
                    should_count = False
            
            if should_count:
                # Calculate day value
                if current_date == start_date and start_day_type != 'full':
                    total_days += Decimal('0.5')
                elif current_date == end_date and end_day_type != 'full':
                    total_days += Decimal('0.5')
                else:
                    total_days += Decimal('1')
                
                leave_dates.append(current_date)
            
            current_date += timedelta(days=1)
        
        return total_days, leave_dates
    
    @classmethod
    def _is_sandwiched(cls, check_date: date, start_date: date, end_date: date) -> bool:
        """Check if a weekend/holiday is sandwiched between leave days"""
        # A day is sandwiched if there are working days before and after
        has_before = check_date > start_date
        has_after = check_date < end_date
        return has_before and has_after
    
    @classmethod
    def _get_holidays(cls, start_date: date, end_date: date, employee = None) -> set:
        """Get holidays in date range"""
        from apps.leave.models import Holiday
        
        holidays_qs = Holiday.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            is_active=True
        )
        if employee and employee.organization_id:
            holidays_qs = holidays_qs.filter(organization=employee.organization)
        
        # Filter by employee location if specified
        if employee and employee.location_id:
            holidays_qs = holidays_qs.filter(
                Q(locations__isnull=True) | Q(locations=employee.location)
            ).distinct()

        if employee and getattr(employee, 'branch_id', None):
            holidays_qs = holidays_qs.filter(
                Q(branch__isnull=True) | Q(branch=employee.branch)
            )
        else:
            holidays_qs = holidays_qs.filter(branch__isnull=True)
        
        return set(holidays_qs.values_list('date', flat=True))


class LeaveBalanceService:
    """
    Manage leave balances:
    - Accruals
    - Carry forward
    - Balance checks
    - Adjustments
    """
    
    @classmethod
    def get_or_create_balance(cls, employee, leave_type, year: int = None):
        """Get or create leave balance for employee and type"""
        from apps.leave.models import LeaveBalance
        
        if year is None:
            year = timezone.now().year
        
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=leave_type,
            organization=employee.organization,
            year=year,
            defaults={
                'opening_balance': Decimal('0'),
                'accrued': Decimal('0'),
            }
        )
        
        return balance
    
    @classmethod
    def get_all_balances(cls, employee, year: int = None) -> List[Dict]:
        """Get all leave balances for an employee"""
        from apps.leave.models import LeaveType, LeaveBalance
        
        if year is None:
            year = timezone.now().year
        
        # Get all active leave types
        leave_types = LeaveType.objects.filter(
            is_active=True,
            organization=employee.organization
        )
        
        balances = []
        for lt in leave_types:
            balance = cls.get_or_create_balance(employee, lt, year)
            balances.append({
                'leave_type': lt,
                'leave_type_id': str(lt.id),
                'leave_type_name': lt.name,
                'leave_type_code': lt.code,
                'color': lt.color,
                'opening_balance': balance.opening_balance,
                'accrued': balance.accrued,
                'taken': balance.taken,
                'carry_forward': balance.carry_forward,
                'adjustment': balance.adjustment,
                'available': balance.available_balance,
            })
        
        return balances
    
    @classmethod
    def check_balance(cls, employee, leave_type, days: Decimal, year: int = None) -> Tuple[bool, str]:
        """
        Check if employee has sufficient leave balance.
        
        Returns:
            (has_balance, message)
        """
        from apps.leave.models import LeavePolicy
        
        if year is None:
            year = timezone.now().year
        
        balance = cls.get_or_create_balance(employee, leave_type, year)
        available = balance.available_balance
        
        if days <= available:
            return True, f"Sufficient balance: {available} days available"
        
        # Check if negative balance allowed
        # Get policy from employee's department or default
        policy = LeavePolicy.objects.filter(
            is_active=True,
            organization=employee.organization
        ).order_by('-created_at').first()
        
        if policy and policy.negative_balance_allowed:
            if (available - days) >= -policy.max_negative_balance:
                return True, f"Negative balance allowed. Will be: {available - days}"
        
        return False, f"Insufficient balance: {available} days available, {days} requested"
    
    @classmethod
    @transaction.atomic
    def deduct_balance(cls, employee, leave_type, days: Decimal, year: int = None):
        """Deduct leave balance after approval"""
        balance = cls.get_or_create_balance(employee, leave_type, year)
        balance.taken += days
        balance.save()
        return balance
    
    @classmethod
    @transaction.atomic
    def restore_balance(cls, employee, leave_type, days: Decimal, year: int = None):
        """Restore leave balance after cancellation"""
        balance = cls.get_or_create_balance(employee, leave_type, year)
        balance.taken -= days
        if balance.taken < 0:
            balance.taken = Decimal('0')
        balance.save()
        return balance

    @classmethod
    @transaction.atomic
    def credit_comp_off_balance(cls, employee, days: Decimal, organization = None):
        """Credit comp-off entitlement to the configured leave type."""
        organization = organization or employee.organization
        from apps.leave.models import LeaveType, COMP_OFF_LEAVE_CODE

        leave_type = LeaveType.objects.filter(
            organization=organization,
            code__iexact=COMP_OFF_LEAVE_CODE,
            is_active=True
        ).first()
        if not leave_type:
            return None

        balance = cls.get_or_create_balance(employee, leave_type, timezone.now().year)
        balance.accrued += Decimal(str(days))
        balance.save()
        return balance
    
    @classmethod
    @transaction.atomic
    def run_monthly_accrual(cls, organization = None):
        """
        Run monthly accrual for all employees.
        Called by Celery scheduled task.
        """
        from apps.leave.models import LeaveType, LeaveBalance
        from apps.employees.models import Employee
        
        current_year = timezone.now().year
        current_month = timezone.now().month
        
        # Get leave types with monthly accrual
        monthly_types = LeaveType.objects.filter(
            accrual_type='monthly',
            is_active=True
        )
        if organization:
            monthly_types = monthly_types.filter(organization=organization)
        
        # Get active employees
        employees = Employee.objects.filter(
            is_active=True,
            is_deleted=False
        )
        if organization:
            employees = employees.filter(organization=organization)
        
        for leave_type in monthly_types:
            monthly_accrual = leave_type.annual_quota / Decimal('12')
            
            for employee in employees:
                # Check if employee is eligible
                if not cls._is_eligible_for_accrual(employee, leave_type):
                    continue
                
                balance = cls.get_or_create_balance(employee, leave_type, current_year)
                balance.accrued += monthly_accrual
                balance.save()
        
        return True
    
    @classmethod
    def _is_eligible_for_accrual(cls, employee, leave_type) -> bool:
        """Check if employee is eligible for accrual"""
        # Check gender applicability
        if leave_type.applicable_gender:
            if employee.user.gender != leave_type.applicable_gender:
                return False
        
        # Check probation period
        if leave_type.applicable_after_months > 0:
            if employee.date_of_joining:
                months = (timezone.now().date() - employee.date_of_joining).days // 30
                if months < leave_type.applicable_after_months:
                    return False
        
        return True
    
    @classmethod
    @transaction.atomic
    def run_year_end_carryforward(cls, from_year: int, to_year: int, organization = None):
        """
        Process year-end carry forward.
        """
        from apps.leave.models import LeaveType, LeaveBalance
        
        carry_forward_types = LeaveType.objects.filter(
            carry_forward_allowed=True,
            is_active=True
        )
        if organization:
            carry_forward_types = carry_forward_types.filter(organization=organization)
        
        for leave_type in carry_forward_types:
            balances = LeaveBalance.objects.filter(
                leave_type=leave_type,
                year=from_year
            )
            if organization:
                balances = balances.filter(organization=organization)
            
            for old_balance in balances:
                available = old_balance.available_balance
                
                # Apply max carry forward limit
                carry_amount = min(available, leave_type.max_carry_forward)
                carry_amount = max(carry_amount, Decimal('0'))
                
                # Create new year balance
                new_balance, _ = LeaveBalance.objects.get_or_create(
                    employee=old_balance.employee,
                    leave_type=leave_type,
                    organization=old_balance.organization,
                    year=to_year,
                    defaults={'carry_forward': carry_amount}
                )
                
                if new_balance.carry_forward == Decimal('0'):
                    new_balance.carry_forward = carry_amount
                    new_balance.save()


class LeaveApprovalService:
    """
    Multi-level approval engine:
    - Level-based approvals
    - Auto approvals
    - Escalations
    - Delegations
    """
    
    @classmethod
    def get_approver(cls, employee, level: int = 1):
        """Get approver for a given level"""
        org_id = employee.organization_id if employee else None

        if level == 1:
            # First level: Reporting manager
            approver = getattr(employee, 'reporting_manager', None)
            if approver and approver.organization_id == org_id:
                return approver
        elif level == 2:
            # Second level: Manager's manager
            manager = getattr(employee, 'reporting_manager', None)
            if manager and manager.reporting_manager and manager.reporting_manager.organization_id == org_id:
                return manager.reporting_manager
        elif level == 3:
            # Third level: HR or department head
            # Could be based on role
            pass
        
        return None
    
    @classmethod
    def get_approval_levels(cls, leave_request) -> int:
        """Determine number of approval levels needed"""
        # Could be based on:
        # - Leave type
        # - Number of days
        # - Employee level
        
        if leave_request.total_days > 5:
            return 2  # Multi-level for long leaves
        
        return 1  # Single level for short leaves
    
    @classmethod
    @transaction.atomic
    def submit_for_approval(cls, leave_request):
        """Submit leave request for approval"""
        from apps.leave.models import LeaveRequest
        
        # Set first approver
        approver = cls.get_approver(leave_request.employee, level=1)
        leave_request.current_approver = approver
        leave_request.status = LeaveRequest.STATUS_PENDING
        leave_request.save()
        
        # Send notification to approver
        if approver:
            from apps.notifications.services import NotificationService
            NotificationService.notify(
                user=approver.user,
                title='New Leave Request',
                message=f'Leave request from {leave_request.employee} for {leave_request.start_date} to {leave_request.end_date}',
                notification_type='info',
                entity_type='leave_request',
                entity_id=leave_request.id
            )
        
        return leave_request
    
    @classmethod
    @transaction.atomic
    def approve(cls, leave_request, approver, comments: str = ''):
        """Approve leave request"""
        from apps.leave.models import LeaveRequest, LeaveApproval
        
        # Get current approval level
        current_level = leave_request.approvals.count() + 1
        total_levels = cls.get_approval_levels(leave_request)
        
        # Create approval record
        LeaveApproval.objects.create(
            leave_request=leave_request,
            approver=approver,
            level=current_level,
            action='approved',
            comments=comments
        )
        
        if current_level >= total_levels:
            # Final approval - update status and deduct balance
            leave_request.status = LeaveRequest.STATUS_APPROVED
            leave_request.current_approver = None
            leave_request.save()
            
            # Send notification to employee
            from apps.notifications.services import NotificationService
            NotificationService.notify(
                user=leave_request.employee.user,
                title='Leave Request Approved',
                message=f'Your leave request from {leave_request.start_date} to {leave_request.end_date} has been approved',
                notification_type='success',
                entity_type='leave_request',
                entity_id=leave_request.id
            )

            from apps.leave.tasks import send_leave_status_email
            send_leave_status_email.delay(str(leave_request.id), 'approved')
        else:
            # Move to next level
            next_approver = cls.get_approver(leave_request.employee, level=current_level + 1)
            leave_request.current_approver = next_approver
            leave_request.save()
            
            # Send notification to next approver
            if next_approver:
                from apps.notifications.services import NotificationService
                NotificationService.notify(
                    user=next_approver.user,
                    title='Leave Request Pending Approval',
                    message=f'Leave request from {leave_request.employee} for {leave_request.start_date} to {leave_request.end_date} is pending your approval',
                    notification_type='info',
                    entity_type='leave_request',
                    entity_id=leave_request.id
                )
        
        return leave_request
    
    @classmethod
    @transaction.atomic
    def reject(cls, leave_request, approver, comments: str = ''):
        """Reject leave request"""
        from apps.leave.models import LeaveRequest, LeaveApproval
        
        current_level = leave_request.approvals.count() + 1
        
        LeaveApproval.objects.create(
            leave_request=leave_request,
            approver=approver,
            level=current_level,
            action='rejected',
            comments=comments
        )
        
        leave_request.status = LeaveRequest.STATUS_REJECTED
        leave_request.current_approver = None
        leave_request.save()
        
        # Send notification to employee
        from apps.notifications.services import NotificationService
        NotificationService.notify(
            user=leave_request.employee.user,
            title='Leave Request Rejected',
            message=f'Your leave request from {leave_request.start_date} to {leave_request.end_date} has been rejected. Reason: {comments}',
            notification_type='error',
            entity_type='leave_request',
            entity_id=leave_request.id
        )

        from apps.leave.tasks import send_leave_status_email
        send_leave_status_email.delay(str(leave_request.id), 'rejected')
        
        return leave_request
    
    @classmethod
    @transaction.atomic
    def cancel(cls, leave_request, reason: str = ''):
        """Cancel leave request (by employee)"""
        from apps.leave.models import LeaveRequest

        leave_request.status = LeaveRequest.STATUS_CANCELLED
        leave_request.current_approver = None
        leave_request.save()
        
        return leave_request
    
    @classmethod
    def get_pending_approvals(cls, approver, organization = None):
        """Get all pending approvals for an approver"""
        from apps.leave.models import LeaveRequest
        
        filters = {
            'current_approver': approver,
            'status': LeaveRequest.STATUS_PENDING,
            'is_active': True,
        }
        if organization:
            filters['organization'] = organization

        return LeaveRequest.objects.filter(**filters).select_related('employee', 'employee__user', 'leave_type')
    
    @classmethod
    def get_team_leaves(cls, manager, start_date: date = None, end_date: date = None, organization = None):
        """Get team leaves for a manager"""
        from apps.leave.models import LeaveRequest
        
        # Get direct reports
        team_ids = list(manager.direct_reports.values_list('id', flat=True))
        
        filters = {
            'employee_id__in': team_ids,
            'status': LeaveRequest.STATUS_APPROVED,
            'is_active': True,
        }
        if organization:
            filters['organization'] = organization

        queryset = LeaveRequest.objects.filter(**filters)
        
        if start_date:
            queryset = queryset.filter(end_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(start_date__lte=end_date)
        
        return queryset.select_related('employee', 'employee__user', 'leave_type')
