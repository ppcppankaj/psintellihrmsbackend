"""
Payroll Services - Calculation Engine and Processing Logic
"""

from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.db import transaction
from .models import (
    EmployeeSalary, PayrollRun, Payslip
)
from apps.attendance.models import AttendanceRecord
from apps.leave.models import LeaveRequest

class PayrollCalculationService:
    """
    Core engine for payroll calculations.
    Handles earnings, deductions, statutory components, and LOP.
    """
    
    @staticmethod
    def calculate_payslip(employee, payroll_run):
        """
        Calculate all components for an individual employee's payslip.
        """
        from apps.core.signals import disable_audit_signals
        with disable_audit_signals():
            import calendar
        
        # 1. Get current compensation structure (Now Flat Model)
        salary = EmployeeSalary.objects.filter(
            employee=employee,
            effective_from__lte=payroll_run.pay_date
        ).first() # OneToOne basically, but filter handles effective_date check simpler? 
        
        # Actually it's OneToOne, so we should just get it.
        # But we might want to check effective_date.
        try:
            salary = employee.salary
            if salary.effective_from > payroll_run.pay_date:
                # If salary starts in future, skip?
                # Or assume current is valid.
                pass 
        except EmployeeSalary.DoesNotExist:
            return None
            
        # 2. Calculate working days and LOP
        _, last_day = calendar.monthrange(payroll_run.year, payroll_run.month)
        start_date = timezone.datetime(payroll_run.year, payroll_run.month, 1).date()
        end_date = timezone.datetime(payroll_run.year, payroll_run.month, last_day).date()
        
        total_days = last_day
        
        # Count LOP days (Absent = 1 day, Half Day = 0.5 day)
        absent_days = AttendanceRecord.objects.filter(
            employee=employee,
            date__range=(start_date, end_date),
            status=AttendanceRecord.STATUS_ABSENT
        ).count()
        
        half_days = AttendanceRecord.objects.filter(
            employee=employee,
            date__range=(start_date, end_date),
            status=AttendanceRecord.STATUS_HALF_DAY
        ).count()
        
        lop_days = Decimal(str(absent_days)) + (Decimal(str(half_days)) * Decimal('0.5'))
        
        # Add unpaid leaves
        unpaid_leaves = LeaveRequest.objects.filter(
            employee=employee,
            start_date__lte=end_date,
            end_date__gte=start_date,
            status='approved',
            leave_type__is_paid=False
        )
        
        for lr in unpaid_leaves:
            o_start = max(start_date, lr.start_date)
            o_end = min(end_date, lr.end_date)
            overlap = (o_end - o_start).days + 1
            lop_days += overlap
            
        days_worked = Decimal(str(total_days)) - Decimal(str(lop_days))
        
        # 3. Calculate adjustment factor
        adjustment_factor = days_worked / Decimal(str(total_days))
        
        # 4. Process individual components (Flat Model Mapping)
        earnings = {}
        deductions = {}
        
        # Explicit Mapping
        earning_fields = [
            'basic', 'hra', 'special_allowance', 'conveyance', 
            'medical_allowance', 'lta', 'performance_bonus'
        ]
        
        basic_salary = Decimal('0.0')
        hra = Decimal('0.0')
        other_allowances = Decimal('0.0')
        
        for field in earning_fields:
            val = getattr(salary, field, Decimal('0.0')) or Decimal('0.0')
            adjusted_val = (val * adjustment_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            if val > 0:
                earnings[field.upper()] = float(adjusted_val)
                
            if field == 'basic':
                basic_salary = adjusted_val
            elif field == 'hra':
                hra = adjusted_val
            else:
                other_allowances += adjusted_val

        # Deductions (Usually Fixed or Percentage)
        # PF Employee
        pf_val = getattr(salary, 'pf_employee', Decimal('0.0')) or Decimal('0.0')
        # If PF is percentage of basic logic is needed, do it here. 
        # But we assume the flat model value is the intended monthly deduction.
        # However, PF usually scales with LOP too if it's on Basic.
        # Let's scale it for now to be safe.
        pf_employee = (pf_val * adjustment_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        deductions['PF_EMPLOYEE'] = float(pf_employee)
        
        # ESI
        esi_val = getattr(salary, 'esi_employee', Decimal('0.0')) or Decimal('0.0')
        esi_employee = (esi_val * adjustment_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        deductions['ESI_EMPLOYEE'] = float(esi_employee)
        
        # Prof Tax (Usually fixed slab, but we should allow it to be 0 if gross is low)
        pt_val = getattr(salary, 'professional_tax', Decimal('0.0')) or Decimal('0.0')
        # Simple logic: If gross is low, PT might be waived. 
        # For now, we use the value from the salary structure.
        deductions['PROF_TAX'] = float(pt_val)
        
        # 6. Sum totals
        gross_salary = sum(Decimal(str(v)) for v in earnings.values())
        
        # Add Leave Encashment
        from apps.leave.models import LeaveEncashment
        approved_encashments = LeaveEncashment.objects.filter(
            employee=employee,
            status=LeaveEncashment.STATUS_APPROVED,
            paid_in_payroll__isnull=True
        )
        
        encashment_total = Decimal('0.0')
        for enc in approved_encashments:
            amt = enc.total_amount or Decimal('0.0')
            encashment_total += amt
            enc.status = LeaveEncashment.STATUS_PROCESSED
            enc.paid_in_payroll = payroll_run
            enc.save()
            
        gross_salary += encashment_total
        total_deductions = sum(Decimal(str(v)) for v in deductions.values())
        net_salary = gross_salary - total_deductions
        
        # 7. Create or update payslip
        payslip, created = Payslip.objects.update_or_create(
            payroll_run=payroll_run,
            employee=employee,
            defaults={
                'total_days': total_days,
                'working_days': int(days_worked),
                'days_worked': days_worked,
                'lop_days': lop_days,
                'basic_salary': basic_salary,
                'hra': hra,
                'other_allowances': other_allowances,
                'leave_encashment': encashment_total,
                'gross_salary': gross_salary,
                'pf_employee': pf_employee,
                'total_deductions': total_deductions,
                'net_salary': net_salary,
                'earnings_breakdown': earnings,
                'deductions_breakdown': deductions,
                'organization': payroll_run.organization
            }
        )
        
        return payslip

    @classmethod
    def process_payroll_run(cls, payroll_run_id):
        """
        Process payroll for all active employees using parallel tasks.
        """
        from .tasks import calculate_single_payslip_task, finalize_payroll_run_task
        from celery import group
        
        payroll_run = PayrollRun.objects.select_related('organization').get(id=payroll_run_id)
        payroll_run.status = PayrollRun.STATUS_PROCESSING
        payroll_run.save()
        
        from apps.employees.models import Employee
        active_employee_ids = list(Employee.objects.filter(
            is_active=True, 
            is_deleted=False
        ).values_list('id', flat=True))
        
        if not active_employee_ids:
            payroll_run.status = PayrollRun.STATUS_PROCESSED
            payroll_run.processed_at = timezone.now()
            payroll_run.save()
            return payroll_run

        # Create a group of tasks and link to a finalizer
        job = group(
            calculate_single_payslip_task.s(emp_id, str(payroll_run_id)) 
            for emp_id in active_employee_ids
        )
        
        # Trigger the group execution
        # Note: In a real system we'd use .apply_async(link=finalize_payroll_run_task.s(str(payroll_run_id)))
        # For simplicity in this architecture refactor, we are setting up the structure.
        result = job.apply_async(link=finalize_payroll_run_task.s(str(payroll_run_id)))
        
        return payroll_run

class SalaryStructureService:
    """
    Deprecated/Simplified Service.
    Auto-calc logic kept for optional API use.
    """
    
    @staticmethod
    def calculate_breakdown(annual_ctc):
        """
        Calculate salary components based on Annual CTC.
        """
        ctc = Decimal(str(annual_ctc))
        monthly_ctc = ctc / Decimal('12')
        
        basic_yearly = ctc * Decimal('0.5')
        basic_monthly = basic_yearly / Decimal('12')
        
        hra_yearly = basic_yearly * Decimal('0.5')
        hra_monthly = hra_yearly / Decimal('12')
        
        pf_employer_yearly = basic_yearly * Decimal('0.12')
        pf_employer_monthly = pf_employer_yearly / Decimal('12')
        
        total_fixed_yearly = basic_yearly + hra_yearly + pf_employer_yearly
        special_allowance_yearly = ctc - total_fixed_yearly
        special_allowance_monthly = special_allowance_yearly / Decimal('12')
        
        if special_allowance_yearly < 0:
            special_allowance_yearly = Decimal('0.0')
            special_allowance_monthly = Decimal('0.0')

        return {
            "annual_ctc": float(ctc.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "monthly_ctc": float(monthly_ctc.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "components": [
                {
                    "code": "BASIC",
                    "name": "Basic Salary",
                    "type": "earning",
                    "monthly": float(basic_monthly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    "annual": float(basic_yearly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                },
                {
                    "code": "HRA",
                    "name": "House Rent Allowance",
                    "type": "earning",
                    "monthly": float(hra_monthly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    "annual": float(hra_yearly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                },
                {
                    "code": "SPECIAL",
                    "name": "Special Allowance",
                    "type": "earning",
                    "monthly": float(special_allowance_monthly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    "annual": float(special_allowance_yearly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                },
                {
                    "code": "PF_EMPLOYER",
                    "name": "PF (Employer)",
                    "type": "statutory",
                    "monthly": float(pf_employer_monthly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    "annual": float(pf_employer_yearly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                }
            ]
        }
