"""
Reports ViewSets - Dashboard and Analytics
Security: Requires authentication and organization/branch isolation
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone
from django.http import FileResponse
from apps.core.openapi_serializers import EmptySerializer

from apps.employees.models import Employee, Department
from apps.recruitment.models import JobPosting, JobApplication
from apps.payroll.models import PayrollRun, Payslip
from apps.core.permissions_branch import BranchPermission, OrganizationFilterBackend
from .permissions import ReportsTenantPermission
from apps.core.throttling import ReportExportThrottle
from .models import ReportTemplate, ScheduledReport, GeneratedReport, ReportExecution
from .serializers import (
    ReportTemplateSerializer,
    ScheduledReportSerializer,
    ReportExecutionSerializer,
    ReportExecuteRequestSerializer,
)
from .services import ReportExecutionService
from .filters import ReportTemplateFilter, ScheduledReportFilter, GeneratedReportFilter, ReportExecutionFilter


class ReportViewSet(viewsets.ViewSet):
    """
    Custom ViewSet for aggregating data across modules for dashboards.
    All reports are filtered by user's organization/branch access.
    """
    permission_classes = [IsAuthenticated, ReportsTenantPermission, BranchPermission]
    serializer_class = EmptySerializer
    
    def _get_branch_filter(self, request):
        """Get branch IDs for filtering"""
        if request.user.is_superuser:
            return None  # No filter for superuser

        if hasattr(request, "_cached_branch_ids"):
            return request._cached_branch_ids

        from apps.authentication.models_hierarchy import BranchUser

        branch_ids = list(
            BranchUser.objects.filter(
                user=request.user,
                is_active=True
            ).values_list("branch_id", flat=True)
        )

        if not branch_ids and hasattr(request.user, "employee") and request.user.employee and request.user.employee.branch_id:
            branch_ids = [request.user.employee.branch_id]

        request._cached_branch_ids = branch_ids
        return branch_ids
    
    def _get_org_filter(self, request):
        """Get organization for filtering"""
        if request.user.is_superuser:
            return None
        return request.user.get_organization()

    @action(detail=False, methods=['get'], url_path='dashboard-metrics')
    def dashboard_metrics(self, request):
        """
        Get high-level statistics for the HR dashboard.
        Filtered by user's organization/branch access.
        """
        branch_ids = self._get_branch_filter(request)
        org = self._get_org_filter(request)
        
        # Build employee filter
        emp_filter = Q(employment_status='active')
        if org:
            emp_filter &= Q(organization=org)
        if branch_ids is not None:
            if not branch_ids:
                return Response({
                    'employees': {'total': 0, 'departments': 0},
                    'recruitment': {'open_jobs': 0, 'new_applications': 0},
                    'payroll': {'last_run': None}
                })
            emp_filter &= Q(branch_id__in=branch_ids)
        
        # Employee stats
        emp_count = Employee.objects.filter(emp_filter).count()
        
        # Department stats (org level)
        dept_filter = Q()
        if org:
            dept_filter = Q(branch__organization=org) | Q(branch__isnull=True)
        dept_count = Department.objects.filter(dept_filter).count() if org else 0
        
        # Recruitment stats
        job_filter = Q(status='open')
        if org:
            job_filter &= Q(organization=org)
        if branch_ids is not None:
            job_filter &= Q(branch_id__in=branch_ids)

        open_jobs = JobPosting.objects.filter(job_filter).count()
        app_filter = Q(stage="new")
        if org:
            app_filter &= Q(organization=org)
        if branch_ids is not None:
            app_filter &= Q(job__branch_id__in=branch_ids)
        new_apps = JobApplication.objects.filter(app_filter).count()

        # Payroll stats
        payroll_filter = Q(status='paid')
        if org:
            payroll_filter &= Q(organization=org)
        if branch_ids is not None:
            payroll_filter &= Q(branch_id__in=branch_ids)
        
        last_run = PayrollRun.objects.filter(payroll_filter).order_by('-pay_date').values('total_net', 'pay_date').first()
        
        data = {
            'employees': {
                'total': emp_count,
                'departments': dept_count,
            },
            'recruitment': {
                'open_jobs': open_jobs,
                'new_applications': new_apps,
            },
            'payroll': {
                'last_run': last_run,
            }
        }
        return Response(data)

    @action(detail=False, methods=['get'], url_path='department-stats')
    def department_stats(self, request):
        """
        Get employee count by department.
        Filtered by user's branch access.
        """
        branch_ids = self._get_branch_filter(request)
        org = self._get_org_filter(request)
        if not org:
            return Response([])
            
        qs = Department.objects.filter(organization=org)
        
        # Annotate with employee count (filtered by branch)
        emp_filter = Q(employees__employment_status='active')
        if branch_ids is not None:
            emp_filter &= Q(employees__branch_id__in=branch_ids)
        
        stats = qs.annotate(
            employee_count=Count('employees', filter=emp_filter)
        ).values('name', 'employee_count')
        
        return Response(list(stats))

    @action(detail=False, methods=['get'], url_path='leave-stats')
    def leave_stats(self, request):
        """
        Get leave utilization stats by leave type.
        Filtered by user's branch access.
        """
        from apps.leave.models import LeaveBalance, LeaveType
        
        branch_ids = self._get_branch_filter(request)
        org = self._get_org_filter(request)
        
        # Get leave types for org
        if not org:
            return Response([])
        # Single grouped aggregation instead of N queries per leave type.
        base_qs = LeaveBalance.objects.filter(organization=org).values(
            "leave_type_id",
            "leave_type__name",
        )
        if branch_ids is not None:
            base_qs = base_qs.filter(employee__branch_id__in=branch_ids)

        aggregates = base_qs.annotate(
            total_taken=Sum("taken"),
            total_accrued=Sum("accrued"),
            total_opening=Sum("opening_balance"),
            total_cf=Sum("carry_forward"),
            total_adj=Sum("adjustment"),
        )

        result = []
        aggregated_ids = set()
        for row in aggregates:
            aggregated_ids.add(row["leave_type_id"])
            taken = row["total_taken"] or 0
            total_credits = (
                (row["total_opening"] or 0)
                + (row["total_accrued"] or 0)
                + (row["total_cf"] or 0)
                + (row["total_adj"] or 0)
            )
            balance = total_credits - taken
            utilization = (taken / total_credits * 100) if total_credits > 0 else 0
            result.append(
                {
                    "leave_type": row["leave_type__name"],
                    "total_taken": float(taken),
                    "total_balance": float(balance),
                    "utilization_percent": round(float(utilization), 1),
                }
            )

        # Keep zero rows for leave types that currently have no balances.
        zero_type_names = LeaveType.objects.filter(organization=org).exclude(id__in=aggregated_ids).values_list("name", flat=True)
        for name in zero_type_names:
            result.append(
                {
                    "leave_type": name,
                    "total_taken": 0.0,
                    "total_balance": 0.0,
                    "utilization_percent": 0.0,
                }
            )

        return Response(result)

    @action(detail=False, methods=['get'])
    def attrition_report(self, request):
        """
        Simple attrition calculation.
        Filtered by user's branch access.
        """
        branch_ids = self._get_branch_filter(request)
        org = self._get_org_filter(request)
        
        # Calculate attrition for accessible branches
        from datetime import timedelta
        
        one_year_ago = timezone.now() - timedelta(days=365)
        
        base_filter = Q()
        if org:
            base_filter &= Q(organization=org)
        if branch_ids is not None:
            base_filter &= Q(branch_id__in=branch_ids)
        
        # Employees at start of period
        start_count = Employee.objects.filter(
            base_filter,
            date_of_joining__lte=one_year_ago
        ).count()
        
        # Employees who left
        left_count = Employee.objects.filter(
            base_filter,
            employment_status='terminated',
            date_of_exit__gte=one_year_ago
        ).count()
        
        attrition_rate = (left_count / start_count * 100) if start_count > 0 else 0
        
        return Response({'attrition_rate': round(attrition_rate, 2)})

    @action(detail=False, methods=['get'])
    def department_diversity(self, request):
        """
        Get employee distribution by department and gender.
        Filtered by user's branch access.
        """
        branch_ids = self._get_branch_filter(request)
        org = self._get_org_filter(request)

        emp_filter = Q()
        if org:
            emp_filter &= Q(organization=org)
        if branch_ids is not None:
            emp_filter &= Q(branch_id__in=branch_ids)
        
        stats = Employee.objects.filter(emp_filter).values(
            'department__name', 'gender'
        ).annotate(count=Count('id'))
        
        return Response(list(stats))

    @action(detail=False, methods=['get'], url_path='analytics/(?P<metric>[^/.]+)')
    def analytics(self, request, metric=None):
        """
        Unified analytics endpoint.
        Routes to specific metric handlers based on the metric path.
        """
        metric_map = {
            'dashboard-metrics': self.dashboard_metrics,
            'department-stats': self.department_stats,
            'leave-stats': self.leave_stats,
            'attrition-report': self.attrition_report,
            'department-diversity': self.department_diversity,
        }
        handler = metric_map.get(metric)
        if not handler:
            return Response(
                {'detail': f'Unknown metric: {metric}'},
                status=status.HTTP_404_NOT_FOUND
            )
        return handler(request)


# -----------------------------------------------------------------------------
# Report Templates / Schedules / Executions
# -----------------------------------------------------------------------------

class ReportTemplateViewSet(viewsets.ModelViewSet):
    """CRUD for report templates"""
    queryset = ReportTemplate.objects.none()
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated, ReportsTenantPermission]
    
    def get_queryset(self):
        return super().get_queryset()
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ReportTemplateFilter
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'created_at']

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)


class ScheduledReportViewSet(viewsets.ModelViewSet):
    """CRUD for scheduled reports"""
    queryset = ScheduledReport.objects.none()
    serializer_class = ScheduledReportSerializer
    permission_classes = [IsAuthenticated, ReportsTenantPermission]
    
    def get_queryset(self):
        return super().get_queryset()
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ScheduledReportFilter
    search_fields = ['template__name', 'schedule']
    ordering_fields = ['created_at', 'last_run']

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)


class ReportExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve report executions"""
    queryset = ReportExecution.objects.none()
    serializer_class = ReportExecutionSerializer
    permission_classes = [IsAuthenticated, ReportsTenantPermission, BranchPermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ReportExecutionFilter
    search_fields = ['template_name', 'template_code', 'requested_by__email']
    ordering_fields = ['created_at', 'completed_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.is_org_admin or user.is_organization_admin():
            return queryset
        return queryset.filter(requested_by=user)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        execution = self.get_object()
        if not execution.file:
            return Response(
                {'detail': 'Report file not available yet'},
                status=status.HTTP_404_NOT_FOUND
            )
        response = FileResponse(execution.file.open('rb'), as_attachment=True)
        return response


class ReportExecuteView(APIView):
    """Execute a report and persist ReportExecution"""
    permission_classes = [IsAuthenticated, ReportsTenantPermission, BranchPermission]
    throttle_classes = [ReportExportThrottle]
    serializer_class = ReportExecuteRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = ReportExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template = ReportExecutionService.get_template(
            template_id=serializer.validated_data.get('template_id'),
            template_code=serializer.validated_data.get('template_code'),
            user=request.user
        )
        if not template:
            return Response({'detail': 'Report template not found'}, status=status.HTTP_404_NOT_FOUND)

        execution = ReportExecutionService.create_execution(
            template=template,
            requested_by=request.user,
            output_format=serializer.validated_data.get('output_format'),
            filters=serializer.validated_data.get('filters', {}),
            parameters=serializer.validated_data.get('parameters', {}),
        )

        if serializer.validated_data.get('run_async'):
            ReportExecutionService.enqueue_execution(execution.id)
            return Response(
                {'success': True, 'data': ReportExecutionSerializer(execution).data},
                status=status.HTTP_202_ACCEPTED
            )

        ReportExecutionService.run_execution(execution, request.user)
        return Response({'success': True, 'data': ReportExecutionSerializer(execution).data})


class ReportExportView(APIView):
    """Execute and immediately return file response"""
    permission_classes = [IsAuthenticated, ReportsTenantPermission, BranchPermission]
    throttle_classes = [ReportExportThrottle]
    serializer_class = ReportExecuteRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = ReportExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template = ReportExecutionService.get_template(
            template_id=serializer.validated_data.get('template_id'),
            template_code=serializer.validated_data.get('template_code'),
            user=request.user
        )
        if not template:
            return Response({'detail': 'Report template not found'}, status=status.HTTP_404_NOT_FOUND)

        execution = ReportExecutionService.create_execution(
            template=template,
            requested_by=request.user,
            output_format=serializer.validated_data.get('output_format'),
            filters=serializer.validated_data.get('filters', {}),
            parameters=serializer.validated_data.get('parameters', {}),
        )

        ReportExecutionService.run_execution(execution, request.user)
        if execution.status != ReportExecution.STATUS_COMPLETED or not execution.file:
            return Response({'success': False, 'data': ReportExecutionSerializer(execution).data})

        response = FileResponse(execution.file.open('rb'), as_attachment=True)
        return response
