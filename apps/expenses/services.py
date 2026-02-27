"""Expense Services - Business Logic"""

from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import (
    ExpenseCategory, ExpenseClaim, ExpenseItem, ExpenseApproval,
    EmployeeAdvance, AdvanceSettlement
)


class ExpenseService:
    """Service class for expense claim operations"""
    
    @staticmethod
    @transaction.atomic
    def create_expense_claim(employee, title, claim_date, expense_from, expense_to,
                             items_data, description=''):
        """Create expense claim with items"""
        claim = ExpenseClaim.objects.create(
            employee=employee,
            title=title,
            description=description,
            claim_date=claim_date,
            expense_from=expense_from,
            expense_to=expense_to,
            status=ExpenseClaim.STATUS_DRAFT
        )
        
        total = Decimal('0')
        for item_data in items_data:
            item = ExpenseItem.objects.create(
                claim=claim,
                category_id=item_data['category'],
                expense_date=item_data['expense_date'],
                description=item_data['description'],
                claimed_amount=item_data['claimed_amount'],
                receipt=item_data.get('receipt'),
                receipt_number=item_data.get('receipt_number', ''),
                vendor_name=item_data.get('vendor_name', ''),
                currency=item_data.get('currency', 'INR'),
                exchange_rate=item_data.get('exchange_rate', Decimal('1'))
            )
            total += item.claimed_amount
        
        claim.total_claimed_amount = total
        claim.save(update_fields=['total_claimed_amount'])
        
        return claim
    
    @staticmethod
    def submit_claim(claim, employee):
        """Submit expense claim for approval"""
        if claim.status != ExpenseClaim.STATUS_DRAFT:
            raise ValueError("Only draft claims can be submitted")
        
        if not claim.items.exists():
            raise ValueError("Claim must have at least one expense item")
        
        # Set current approver (reporting manager)
        claim.current_approver = employee.reporting_manager
        claim.status = ExpenseClaim.STATUS_SUBMITTED
        claim.save(update_fields=['status', 'current_approver'])
        
        return claim
    
    @staticmethod
    @transaction.atomic
    def process_approval(claim, approver, action, comments='', item_adjustments=None):
        """Process approval/rejection of expense claim"""
        if claim.status not in [ExpenseClaim.STATUS_SUBMITTED, ExpenseClaim.STATUS_PENDING_APPROVAL]:
            raise ValueError("Claim is not pending approval")
        
        # Get current approval level
        current_level = claim.approvals.count() + 1
        
        if action == 'approve':
            # Apply item adjustments if any
            if item_adjustments:
                for adj in item_adjustments:
                    item = claim.items.get(id=adj['item_id'])
                    item.approved_amount = adj.get('approved_amount', item.claimed_amount)
                    item.is_approved = True
                    item.save()
            else:
                # Approve all items as claimed
                claim.items.update(is_approved=True)
                for item in claim.items.all():
                    item.approved_amount = item.claimed_amount
                    item.save()
            
            # Create approval record
            ExpenseApproval.objects.create(
                claim=claim,
                approver=approver,
                level=current_level,
                action='approved',
                comments=comments
            )
            
            # Update claim
            claim.status = ExpenseClaim.STATUS_APPROVED
            claim.approved_by = approver
            claim.approved_at = timezone.now()
            claim.update_totals()
            claim.save(update_fields=['status', 'approved_by', 'approved_at'])
            
        elif action == 'reject':
            ExpenseApproval.objects.create(
                claim=claim,
                approver=approver,
                level=current_level,
                action='rejected',
                comments=comments
            )
            
            claim.status = ExpenseClaim.STATUS_REJECTED
            claim.rejection_reason = comments
            claim.save(update_fields=['status', 'rejection_reason'])
            
        elif action == 'return':
            ExpenseApproval.objects.create(
                claim=claim,
                approver=approver,
                level=current_level,
                action='returned',
                comments=comments
            )
            
            claim.status = ExpenseClaim.STATUS_DRAFT
            claim.save(update_fields=['status'])
        
        return claim
    
    @staticmethod
    @transaction.atomic
    def process_payment(claim, paid_by, amount, payment_mode, payment_reference='',
                       advance_to_adjust=None):
        """Process payment for approved expense claim"""
        if claim.status != ExpenseClaim.STATUS_APPROVED:
            raise ValueError("Only approved claims can be paid")
        
        now = timezone.now()
        
        # Adjust against advance if provided
        advance_adjustment = Decimal('0')
        if advance_to_adjust:
            advance = EmployeeAdvance.objects.get(id=advance_to_adjust)
            if advance.employee_id != claim.employee_id:
                raise ValueError("Advance belongs to different employee")
            if advance.remaining_balance > 0:
                advance_adjustment = min(advance.remaining_balance, amount)
                
                # Create settlement
                AdvanceSettlement.objects.create(
                    advance=advance,
                    settlement_type=AdvanceSettlement.SETTLEMENT_EXPENSE,
                    amount=advance_adjustment,
                    settlement_date=now.date(),
                    expense_claim=claim,
                    notes=f"Adjusted against expense claim {claim.claim_number}"
                )
        
        actual_payment = amount - advance_adjustment
        
        claim.advance_adjusted = advance_adjustment
        claim.total_paid_amount = claim.total_paid_amount + actual_payment + advance_adjustment
        claim.paid_by = paid_by
        claim.paid_at = now
        claim.payment_reference = payment_reference
        claim.payment_mode = payment_mode
        
        if claim.total_paid_amount >= claim.total_approved_amount:
            claim.payment_status = ExpenseClaim.PAYMENT_PAID
            claim.status = ExpenseClaim.STATUS_PAID
        else:
            claim.payment_status = ExpenseClaim.PAYMENT_PARTIALLY_PAID
        
        claim.save()
        
        return claim
    
    @staticmethod
    def get_employee_expense_summary(employee, year=None):
        """Get expense summary for an employee"""
        if year is None:
            year = timezone.now().year
        
        claims = ExpenseClaim.objects.filter(
            employee=employee,
            claim_date__year=year
        )
        
        from django.db.models import Sum, Count
        
        summary = claims.aggregate(
            total_claimed=Sum('total_claimed_amount'),
            total_approved=Sum('total_approved_amount'),
            total_paid=Sum('total_paid_amount'),
            claim_count=Count('id')
        )
        
        # By category
        category_breakdown = ExpenseItem.objects.filter(
            claim__employee=employee,
            claim__claim_date__year=year
        ).values('category__name').annotate(
            total=Sum('claimed_amount'),
            count=Count('id')
        ).order_by('-total')
        
        return {
            'summary': summary,
            'by_category': list(category_breakdown)
        }


class AdvanceService:
    """Service class for employee advance operations"""
    
    @staticmethod
    def create_advance_request(employee, purpose, advance_date, amount,
                               settlement_type='expense', deduction_start_month=None,
                               monthly_deduction_amount=None):
        """Create advance request"""
        advance = EmployeeAdvance.objects.create(
            employee=employee,
            purpose=purpose,
            advance_date=advance_date,
            amount=amount,
            remaining_balance=amount,
            settlement_type=settlement_type,
            deduction_start_month=deduction_start_month,
            monthly_deduction_amount=monthly_deduction_amount,
            status=EmployeeAdvance.STATUS_PENDING
        )
        return advance
    
    @staticmethod
    def approve_advance(advance, approved_by, action='approve', comments=''):
        """Approve or reject advance request"""
        if advance.status != EmployeeAdvance.STATUS_PENDING:
            raise ValueError("Advance is not pending approval")
        
        now = timezone.now()
        
        if action == 'approve':
            advance.status = EmployeeAdvance.STATUS_APPROVED
            advance.approved_by = approved_by
            advance.approved_at = now
        elif action == 'reject':
            advance.status = EmployeeAdvance.STATUS_REJECTED
            advance.rejection_reason = comments
        
        advance.save()
        return advance
    
    @staticmethod
    def disburse_advance(advance, disbursed_by, disbursement_mode, disbursement_reference=''):
        """Disburse approved advance"""
        if advance.status != EmployeeAdvance.STATUS_APPROVED:
            raise ValueError("Advance is not approved")
        
        advance.status = EmployeeAdvance.STATUS_DISBURSED
        advance.disbursed_by = disbursed_by
        advance.disbursed_at = timezone.now()
        advance.disbursement_mode = disbursement_mode
        advance.disbursement_reference = disbursement_reference
        advance.save()
        
        return advance
    
    @staticmethod
    def get_pending_advances(employee):
        """Get unsettled advances for an employee"""
        return EmployeeAdvance.objects.filter(
            employee=employee,
            status=EmployeeAdvance.STATUS_DISBURSED,
            remaining_balance__gt=0
        ).order_by('advance_date')
    
    @staticmethod
    def create_salary_settlement(advance, payslip, amount):
        """Create settlement from salary deduction"""
        if amount > advance.remaining_balance:
            raise ValueError("Settlement amount exceeds remaining balance")
        
        settlement = AdvanceSettlement.objects.create(
            advance=advance,
            settlement_type=AdvanceSettlement.SETTLEMENT_SALARY,
            amount=amount,
            settlement_date=timezone.now().date(),
            payslip=payslip,
            notes=f"Salary deduction for {payslip.payroll_run.month}/{payslip.payroll_run.year}"
        )
        
        return settlement
