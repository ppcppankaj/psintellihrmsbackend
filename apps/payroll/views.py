"""
Payroll ViewSets
Security: Requires authentication and branch-level isolation
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.db.models import Q
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    EmployeeSalary,
    PayrollRun, Payslip, TaxDeclaration, ReimbursementClaim,
    EmployeeLoan, LoanRepayment
)
from .serializers import (
    EmployeeSalarySerializer, PayrollRunSerializer,
    PayslipSerializer, PayslipListSerializer, TaxDeclarationSerializer,
    ReimbursementClaimSerializer, ReimbursementClaimListSerializer,
    SalaryRevisionSerializer, EmployeeLoanSerializer, EmployeeLoanListSerializer,
    LoanRepaymentSerializer
)
from .filters import (
    EmployeeSalaryFilter, PayrollRunFilter, PayslipFilter,
    TaxDeclarationFilter, ReimbursementClaimFilter, EmployeeLoanFilter,
)
from .services import PayrollCalculationService

from apps.core.tenant_guards import OrganizationViewSetMixin
from apps.core.permissions_branch import BranchFilterBackend, BranchPermission
from .permissions import PayrollTenantPermission


class BranchFilterMixin:
    """Mixin to add branch filtering to payroll viewsets"""
    
    def get_branch_ids(self):
        """Get branch IDs for current user"""
        if self.request.user.is_superuser:
            return None  # No filter
        
        from apps.authentication.models_hierarchy import BranchUser
        return list(BranchUser.objects.filter(
            user=self.request.user,
            is_active=True
        ).values_list('branch_id', flat=True))


# Note: SalaryComponentViewSet and SalaryStructureViewSet are REMOVED as tables are deleted.

class EmployeeCompensationViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Manages Employee Salary Structures.
    Branch-scoped through employee relationship.
    """
    queryset = EmployeeSalary.objects.none()
    serializer_class = EmployeeSalarySerializer
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EmployeeSalaryFilter
    ordering_fields = ['employee', 'annual_ctc', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by user's accessible branches"""
        queryset = super().get_queryset().select_related('employee', 'employee__user')
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)
    
    def create(self, request, *args, **kwargs):
        """
        Handle creation of salary structure.
        Implements UPSERT logic: If structure exists for employee, update it.
        """
        try:
            employee_id = request.data.get('employee')
            
            # Standard creation if no employee_id (let validator handle)
            if not employee_id:
                return super().create(request, *args, **kwargs)
                
            # Check for existing record including soft-deleted ones
            # EmployeeSalary uses SoftDeleteManager, so default objects.get() misses deleted ones.
            # Using all_with_deleted() to find potential conflicts.
            # Note: We filter() then first() to avoid MultipleObjectsReturned (though OneToOne prevents duplicates usually)
            instance = EmployeeSalary.objects.all_with_deleted().filter(employee=employee_id).first()
            
            if instance:
                # If found, check if it's soft-deleted
                if getattr(instance, 'is_deleted', False):
                    instance.restore() # Restore soft-deleted record
                
                # Perform update
                serializer = self.get_serializer(instance, data=request.data)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                return Response(serializer.data)
            
            else:
                # If genuinely not exists, create new
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        except Exception as e:
            # Capture full traceback for debugging
            import traceback
            error_details = traceback.format_exc()
            print(f"CRITICAL ERROR IN SALARY SAVE: {error_details}")
            return Response(
                {"error": str(e), "traceback": error_details}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], url_path='calculate-structure')
    def calculate_structure(self, request):
        """Calculate salary structure breakdown based on CTC"""
        annual_ctc = request.data.get('annual_ctc')
        if not annual_ctc:
            return Response({"error": "Annual CTC is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from .services import SalaryStructureService
            breakdown = SalaryStructureService.calculate_breakdown(annual_ctc)
            return Response(breakdown)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='my-compensation')
    def my_compensation(self, request):
        """Get current compensation for the logged-in employee"""
        if not hasattr(request.user, 'employee'):
            return Response({"error": "No employee profile found"}, status=404)
            
        # OneToOne, so simple access
        try:
            salary = request.user.employee.salary # Related name 'salary'
        except EmployeeSalary.DoesNotExist:
            return Response({"error": "No active compensation found"}, status=404)
            
        serializer = self.get_serializer(salary)
        return Response(serializer.data)


class PayrollRunViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Payroll run management.
    Branch-scoped - each payroll run belongs to a branch.
    """
    queryset = PayrollRun.objects.none()
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PayrollRunFilter
    search_fields = ['branch__name']
    ordering_fields = ['month', 'year', 'status', 'created_at']
    ordering = ['-year', '-month']
    
    def get_queryset(self):
        """Filter by user's accessible branches"""
        queryset = super().get_queryset()
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(branch_id__in=branch_ids)
    
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process payroll for all employees in this run"""
        payroll_run = self.get_object()
        if payroll_run.status not in [PayrollRun.STATUS_DRAFT, PayrollRun.STATUS_PROCESSING]:
            return Response(
                {"error": "Payroll run is not in a processable state"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        payroll_run = PayrollCalculationService.process_payroll_run(payroll_run.id)
        serializer = self.get_serializer(payroll_run)
        return Response(serializer.data)
        
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a processed payroll run"""
        payroll_run = self.get_object()
        if payroll_run.status != PayrollRun.STATUS_PROCESSED:
            return Response(
                {"error": "Only processed payroll runs can be approved"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        payroll_run.status = PayrollRun.STATUS_APPROVED
        payroll_run.approved_at = timezone.now()
        if hasattr(request.user, 'employee'):
            payroll_run.approved_by = request.user.employee
        payroll_run.save()
        
        serializer = self.get_serializer(payroll_run)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """Lock an approved payroll run to prevent further changes.
        Triggers async payslip PDF generation and employee email notification.
        """
        payroll_run = self.get_object()
        if payroll_run.status != PayrollRun.STATUS_APPROVED:
            return Response(
                {"error": "Only approved payroll runs can be locked"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payroll_run.status = PayrollRun.STATUS_LOCKED
        payroll_run.locked_at = timezone.now()
        payroll_run.save()

        # 🚀 Async: generate payslip PDFs and email employees
        from .tasks import generate_payslip_pdfs_and_notify
        org = getattr(request, 'organization', None)
        if org:
            generate_payslip_pdfs_and_notify.delay(str(org.id), str(payroll_run.id))
        
        serializer = self.get_serializer(payroll_run)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """Mark a locked payroll run as paid"""
        payroll_run = self.get_object()
        if payroll_run.status != PayrollRun.STATUS_LOCKED:
            return Response(
                {"error": "Only locked payroll runs can be marked as paid"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payroll_run.status = PayrollRun.STATUS_PAID
        payroll_run.paid_at = timezone.now()
        payroll_run.save()
        
        serializer = self.get_serializer(payroll_run)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='export-pf')
    def export_pf(self, request, pk=None):
        """Export PF contribution report for compliance"""
        import csv
        from django.http import HttpResponse
        from .models import PFContribution
        
        payroll_run = self.get_object()
        payslips = payroll_run.payslips.select_related('employee', 'employee__user').all()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="pf_report_{payroll_run.month}_{payroll_run.year}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'UAN', 'Member Name', 'Gross Wages', 'EPF Wages', 'EPS Wages',
            'EDLI Wages', 'EPF Employee', 'EPS Employer', 'EPF Employer Diff',
            'NCP Days', 'Refund of Advances'
        ])
        
        for payslip in payslips:
            try:
                pf = payslip.pf_contribution
                writer.writerow([
                    pf.uan,
                    payslip.employee.user.full_name,
                    payslip.gross_salary,
                    pf.pf_wages,
                    pf.pf_wages,
                    pf.pf_wages,
                    pf.epf_employee,
                    pf.eps,
                    pf.epf_employer - pf.eps,
                    0,
                    0
                ])
            except PFContribution.DoesNotExist:
                continue
        
        return response

    @action(detail=True, methods=['get'], url_path='export-esi')
    def export_esi(self, request, pk=None):
        """Export ESI contribution report for compliance"""
        import csv
        from django.http import HttpResponse
        
        payroll_run = self.get_object()
        payslips = payroll_run.payslips.select_related('employee', 'employee__user').all()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="esi_report_{payroll_run.month}_{payroll_run.year}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'IP Number', 'IP Name', 'No of Days Worked', 'Total Wages',
            'IP Contribution', 'Employer Contribution', 'Total Contribution'
        ])
        
        for payslip in payslips:
            salary_snap = payslip.salary_snapshot or {}
            esi_employee = salary_snap.get('esi_employee', 0)
            esi_employer = salary_snap.get('esi_employer', 0)
            
            if esi_employee > 0 or esi_employer > 0:
                writer.writerow([
                    payslip.employee.employee_id,
                    payslip.employee.user.full_name,
                    payslip.attendance_snapshot.get('days_worked', 0),
                    payslip.gross_salary,
                    esi_employee,
                    esi_employer,
                    esi_employee + esi_employer
                ])
        
        return response

    @action(detail=True, methods=['get'], url_path='export-pt')
    def export_pt(self, request, pk=None):
        """Export Professional Tax report for compliance"""
        import csv
        from django.http import HttpResponse
        
        payroll_run = self.get_object()
        payslips = payroll_run.payslips.select_related('employee', 'employee__user').all()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="pt_report_{payroll_run.month}_{payroll_run.year}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee ID', 'Employee Name', 'PAN', 'State',
            'Gross Salary', 'Professional Tax'
        ])
        
        for payslip in payslips:
            salary_snap = payslip.salary_snapshot or {}
            pt = salary_snap.get('professional_tax', 0)
            
            if pt > 0:
                writer.writerow([
                    payslip.employee.employee_id,
                    payslip.employee.user.full_name,
                    getattr(payslip.employee, 'pan_number', ''),
                    getattr(payslip.employee, 'state', ''),
                    payslip.gross_salary,
                    pt
                ])
        
        return response


class PayslipViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Payslip viewing.
    Branch-scoped through employee relationship.
    """
    queryset = Payslip.objects.none()
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PayslipFilter
    ordering_fields = ['gross_salary', 'net_salary', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by user's accessible branches"""
        queryset = super().get_queryset()
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PayslipListSerializer
        return PayslipSerializer

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get payroll summary for dashboard using efficient DB aggregation"""
        employee = getattr(request.user, 'employee', None)
        if not employee:
            return Response({"error": "No employee record found"}, status=404)
            
        now = timezone.now()
        current_year = now.year
        current_month = now.month
        
        latest_payslip = self.get_queryset().filter(
            employee=employee,
            payroll_run__status='paid',
            organization=getattr(request, 'organization', None)
        ).order_by('-payroll_run__year', '-payroll_run__month').first()
        
        current_net = latest_payslip.net_salary if latest_payslip else 0
        last_salary_date = latest_payslip.payroll_run.pay_date if latest_payslip else None
        
        # YTD Gross & Tax (Financial Year: April to March)
        if current_month >= 4:
            fy_start_year = current_year
        else:
            fy_start_year = current_year - 1
            
        from django.db.models import Sum
        
        ytd_stats = self.get_queryset().filter(
            employee=employee,
            payroll_run__status='paid',
            organization=getattr(request, 'organization', None)
        ).filter(
            Q(payroll_run__year=fy_start_year, payroll_run__month__gte=4) | 
            Q(payroll_run__year=fy_start_year + 1, payroll_run__month__lte=3)
        ).aggregate(
            total_gross=Sum('gross_salary'),
            total_tax=Sum('tds')
        )
        
        ytd_gross = ytd_stats['total_gross'] or 0
        ytd_tax = ytd_stats['total_tax'] or 0
        
        # Pending Reimbursements
        pending_amount = 0
        try:
            from apps.expenses.models import Expense
            pending_stats = Expense.objects.filter(
                employee=employee,
                status='approved',
                is_reimbursed=False
            ).aggregate(total=Sum('amount'))
            pending_amount = pending_stats['total'] or 0
        except Exception:
            pending_amount = 0

        return Response({
            "current_month_net": current_net,
            "ytd_gross": ytd_gross,
            "ytd_tax": ytd_tax,
            "pending_reimbursements": pending_amount,
            "last_salary_date": last_salary_date
        })

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download payslip as PDF"""
        payslip = self.get_object()
        
        # Check if user has access to this payslip
        if not request.user.is_superuser:
            if hasattr(request.user, 'employee') and request.user.employee != payslip.employee:
                # Check if user has HR/Manager access to this employee's branch
                branch_ids = self.get_branch_ids()
                if branch_ids and payslip.employee.branch_id not in branch_ids:
                    return Response(
                        {"error": "You don't have access to this payslip"},
                        status=status.HTTP_403_FORBIDDEN
                    )
        
        # Check if PDF file exists
        if payslip.pdf_file and payslip.pdf_file.name:
            try:
                response = FileResponse(
                    payslip.pdf_file.open('rb'),
                    content_type='application/pdf'
                )
                filename = f"payslip_{payslip.employee.employee_id}_{payslip.payroll_run.month}_{payslip.payroll_run.year}.pdf"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            except FileNotFoundError:
                pass
        
        # Generate PDF on-the-fly if not stored
        from .services import PayslipPDFService
        try:
            pdf_content = PayslipPDFService.generate_payslip_pdf(payslip)
            response = Response(pdf_content, content_type='application/pdf')
            filename = f"payslip_{payslip.employee.employee_id}_{payslip.payroll_run.month}_{payslip.payroll_run.year}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return Response(
                {"error": f"Could not generate payslip PDF: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TaxDeclarationViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Tax declaration management.
    Branch-scoped through employee relationship.
    """
    queryset = TaxDeclaration.objects.none()
    serializer_class = TaxDeclarationSerializer
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TaxDeclarationFilter
    search_fields = ['employee__employee_id', 'employee__user__full_name']
    ordering_fields = ['financial_year', 'created_at']
    ordering = ['-financial_year']
    
    def get_queryset(self):
        """Filter by user's accessible branches"""
        queryset = super().get_queryset()
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)


class ReimbursementClaimViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Reimbursement claim management.
    Branch-scoped through employee relationship.
    """
    queryset = ReimbursementClaim.objects.none()
    serializer_class = ReimbursementClaimSerializer
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReimbursementClaimFilter
    search_fields = ['title', 'employee__user__full_name']
    ordering_fields = ['amount', 'status', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by user's accessible branches"""
        queryset = super().get_queryset().select_related('employee', 'employee__user')
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ReimbursementClaimListSerializer
        return ReimbursementClaimSerializer
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit a draft reimbursement claim"""
        claim = self.get_object()
        if claim.status != ReimbursementClaim.STATUS_DRAFT:
            return Response(
                {"error": "Only draft claims can be submitted"},
                status=status.HTTP_400_BAD_REQUEST
            )
        claim.status = ReimbursementClaim.STATUS_SUBMITTED
        claim.submitted_at = timezone.now()
        claim.save()
        return Response(ReimbursementClaimSerializer(claim).data)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a submitted reimbursement claim"""
        claim = self.get_object()
        if claim.status != ReimbursementClaim.STATUS_SUBMITTED:
            return Response(
                {"error": "Only submitted claims can be approved"},
                status=status.HTTP_400_BAD_REQUEST
            )
        claim.status = ReimbursementClaim.STATUS_APPROVED
        claim.approved_at = timezone.now()
        claim.save()
        return Response(ReimbursementClaimSerializer(claim).data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a submitted reimbursement claim"""
        claim = self.get_object()
        if claim.status != ReimbursementClaim.STATUS_SUBMITTED:
            return Response(
                {"error": "Only submitted claims can be rejected"},
                status=status.HTTP_400_BAD_REQUEST
            )
        claim.status = ReimbursementClaim.STATUS_REJECTED
        claim.save()
        return Response(ReimbursementClaimSerializer(claim).data)
    
    @action(detail=False, methods=['get'], url_path='my-claims')
    def my_claims(self, request):
        """Get current user's reimbursement claims"""
        if not hasattr(request.user, 'employee'):
            return Response({"error": "No employee profile found"}, status=404)
        
        claims = ReimbursementClaim.objects.filter(
            employee=request.user.employee,
            organization=getattr(request, 'organization', None)
        )
        serializer = ReimbursementClaimListSerializer(claims, many=True)
        return Response(serializer.data)


class SalaryRevisionViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Salary revision history.
    Shows all salary structures (active and historical) for employees.
    """
    queryset = EmployeeSalary.objects.none()
    serializer_class = SalaryRevisionSerializer
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EmployeeSalaryFilter
    search_fields = ['employee__employee_id', 'employee__user__full_name']
    ordering_fields = ['effective_from', 'annual_ctc', 'created_at']
    ordering = ['-effective_from']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('employee', 'employee__user')
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)

    @action(detail=False, methods=['get'], url_path='by-employee/(?P<employee_id>[^/.]+)')
    def by_employee(self, request, employee_id=None):
        """Get salary revision history for a specific employee"""
        revisions = self.get_queryset().filter(employee_id=employee_id).order_by('-effective_from')
        serializer = self.get_serializer(revisions, many=True)
        return Response(serializer.data)


class LoanViewSet(BranchFilterMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Employee loan management.
    Includes CRUD + disburse/repay actions.
    """
    queryset = EmployeeLoan.objects.none()
    serializer_class = EmployeeLoanSerializer
    permission_classes = [IsAuthenticated, PayrollTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EmployeeLoanFilter
    search_fields = ['employee__employee_id', 'employee__user__full_name']
    ordering_fields = ['amount', 'status', 'loan_type', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('employee', 'employee__user')
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        branch_ids = self.get_branch_ids()
        
        if branch_ids is None:
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)

    def get_serializer_class(self):
        if self.action == 'list':
            return EmployeeLoanListSerializer
        return EmployeeLoanSerializer

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a pending loan request"""
        loan = self.get_object()
        if loan.status != EmployeeLoan.STATUS_PENDING:
            return Response(
                {"error": "Only pending loans can be approved"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        loan.status = EmployeeLoan.STATUS_APPROVED
        loan.approved_at = timezone.now()
        if hasattr(request.user, 'employee'):
            loan.approved_by = request.user.employee
        loan.save()
        
        return Response(EmployeeLoanSerializer(loan).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a pending loan request"""
        loan = self.get_object()
        if loan.status != EmployeeLoan.STATUS_PENDING:
            return Response(
                {"error": "Only pending loans can be rejected"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        loan.status = EmployeeLoan.STATUS_REJECTED
        loan.save()
        
        return Response(EmployeeLoanSerializer(loan).data)

    @action(detail=True, methods=['post'])
    def disburse(self, request, pk=None):
        """Disburse an approved loan"""
        loan = self.get_object()
        if loan.status != EmployeeLoan.STATUS_APPROVED:
            return Response(
                {"error": "Only approved loans can be disbursed"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        loan.status = EmployeeLoan.STATUS_DISBURSED
        loan.disbursed_at = timezone.now()
        loan.save()
        
        return Response(EmployeeLoanSerializer(loan).data)

    @action(detail=True, methods=['post'])
    def repay(self, request, pk=None):
        """Record a loan repayment"""
        loan = self.get_object()
        if loan.status not in [EmployeeLoan.STATUS_DISBURSED, EmployeeLoan.STATUS_REPAYING]:
            return Response(
                {"error": "Loan must be disbursed to record repayment"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        amount = request.data.get('amount')
        if not amount:
            return Response(
                {"error": "Repayment amount is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from decimal import Decimal
        repayment = LoanRepayment.objects.create(
            loan=loan,
            amount=Decimal(str(amount)),
            repayment_date=timezone.now().date(),
            remarks=request.data.get('remarks', ''),
            organization=loan.organization
        )
        
        if loan.status == EmployeeLoan.STATUS_DISBURSED:
            loan.status = EmployeeLoan.STATUS_REPAYING
            loan.save()
        
        return Response({
            "loan": EmployeeLoanSerializer(loan).data,
            "repayment": LoanRepaymentSerializer(repayment).data
        })

    @action(detail=True, methods=['get'])
    def repayments(self, request, pk=None):
        """Get all repayments for a loan"""
        loan = self.get_object()
        repayments = loan.repayments.all()
        serializer = LoanRepaymentSerializer(repayments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-loans')
    def my_loans(self, request):
        """Get current user's loans"""
        if not hasattr(request.user, 'employee'):
            return Response({"error": "No employee profile found"}, status=404)
        
        loans = EmployeeLoan.objects.filter(
            employee=request.user.employee,
            organization=getattr(request, 'organization', None)
        )
        serializer = EmployeeLoanListSerializer(loans, many=True)
        return Response(serializer.data)
