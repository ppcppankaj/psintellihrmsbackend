"""
Leave Views - Leave Management APIs
"""

from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions import HasPermission, IsSelfOrHasPermission
from apps.core.permissions_branch import BranchFilterBackend, BranchPermission
from apps.core.tenant_guards import OrganizationViewSetMixin
from apps.core.mixins import BulkImportExportMixin

from .models import (
    LeaveType,
    LeavePolicy,
    LeaveBalance,
    LeaveRequest,
    LeaveApproval,
    Holiday,
    LeaveEncashment,
    CompensatoryLeave,
)
from .serializers import (
    LeaveTypeSerializer, LeavePolicySerializer, LeaveBalanceSerializer,
    LeaveRequestListSerializer, LeaveRequestDetailSerializer,
    LeaveApplySerializer, LeaveApproveSerializer, LeaveCancelSerializer,
    LeaveBalanceSummarySerializer, LeaveCalculateSerializer,
    LeaveCalculateResponseSerializer, HolidaySerializer, TeamLeaveSerializer,
    LeaveEncashmentSerializer, CompensatoryLeaveSerializer,
    HolidayBulkImportSerializer
)
from .permissions import LeaveTenantPermission
from .filters import (
    LeaveTypeFilter, LeavePolicyFilter, LeaveRequestFilter,
    LeaveBalanceFilter, HolidayFilter, LeaveEncashmentFilter,
    CompensatoryLeaveFilter,
)
from .services import LeaveCalculationService, LeaveBalanceService, LeaveApprovalService


class LeaveTypeViewSet(BulkImportExportMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Leave type management"""
    
    queryset = LeaveType.objects.none()
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAuthenticated, HasPermission, LeaveTenantPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LeaveTypeFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return LeaveType.objects.none()
        return LeaveType.objects.filter(
            organization=organization,
            is_active=True
        ).order_by('name')

    def perform_create(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError('Organization context missing')
        serializer.save(organization=organization, created_by=self.request.user)

    def perform_update(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError('Organization context missing')
        serializer.save(organization=organization, updated_by=self.request.user)
    # pagination_class = None  # Enforce default pagination
    
    permission_map = {
        'list': ['leave.view'],
        'retrieve': ['leave.view'],
        'create': ['leave.manage_types'],
        'update': ['leave.manage_types'],
        'partial_update': ['leave.manage_types'],
        'destroy': ['leave.manage_types'],
    }


class LeavePolicyViewSet(BulkImportExportMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Leave policy management"""
    
    queryset = LeavePolicy.objects.none()
    serializer_class = LeavePolicySerializer
    permission_classes = [IsAuthenticated, HasPermission, LeaveTenantPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LeavePolicyFilter
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return LeavePolicy.objects.none()
        return LeavePolicy.objects.filter(
            organization=organization,
            is_active=True
        ).order_by('name')

    def perform_create(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError('Organization context missing')
        serializer.save(organization=organization, created_by=self.request.user)

    def perform_update(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError('Organization context missing')
        serializer.save(organization=organization, updated_by=self.request.user)
    
    permission_map = {
        'list': ['leave.view'],
        'retrieve': ['leave.view'],
        'create': ['leave.manage_policies'],
        'update': ['leave.manage_policies'],
        'partial_update': ['leave.manage_policies'],
        'destroy': ['leave.manage_policies'],
    }


class LeaveRequestViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Leave request management - apply, approve, cancel"""
    
    queryset = LeaveRequest.objects.select_related(
        'employee', 'employee__user', 'leave_type', 'branch', 'current_approver'
    )
    permission_classes = [IsAuthenticated, BranchPermission, LeaveTenantPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LeaveRequestFilter
    search_fields = ['employee__employee_id', 'employee__user__full_name', 'reason']
    ordering_fields = ['start_date', 'end_date', 'status', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return LeaveRequestListSerializer
        if self.action == 'apply':
            return LeaveApplySerializer
        return LeaveRequestDetailSerializer
    
    def get_employee(self, request):
        """Helper to get employee profile for current user"""
        if not hasattr(request, '_employee'):
            from apps.employees.models import Employee
            organization = getattr(request, 'organization', None)
            queryset = Employee.objects.filter(user=request.user)
            if organization:
                queryset = queryset.filter(organization=organization)
            request._employee = queryset.first()
        return request._employee

    def perform_create(self, serializer):
        organization = getattr(self.request, 'organization', None)
        employee = serializer.validated_data.get('employee')
        leave_type = serializer.validated_data.get('leave_type')

        if not organization:
            raise ValidationError('Organization context missing')
        if not employee:
            raise ValidationError({'employee': 'Employee is required'})
        if employee.organization_id != organization.id:
            raise ValidationError({'employee': 'Employee not in this organization'})
        if leave_type and leave_type.organization_id != organization.id:
            raise ValidationError({'leave_type': 'Leave type not in this organization'})

        serializer.save(organization=organization, created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.status == LeaveRequest.STATUS_APPROVED:
            raise ValidationError('Approved leave requests cannot be modified')
        organization = getattr(self.request, 'organization', None)
        serializer.save(organization=organization, updated_by=self.request.user)

    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return LeaveRequest.objects.none()

        queryset = LeaveRequest.objects.filter(
            organization=organization,
            is_active=True
        ).select_related(
            'employee',
            'employee__user',
            'leave_type',
            'branch',
            'current_approver',
        )

        user = self.request.user
        if not user.has_permission_for('leave.view_all'):
            if user.has_permission_for('leave.view_team') and hasattr(user, 'employee'):
                team_ids = list(user.employee.direct_reports.values_list('id', flat=True))
                team_ids.append(user.employee.id)
                queryset = queryset.filter(employee_id__in=team_ids)
            elif hasattr(user, 'employee'):
                queryset = queryset.filter(employee=user.employee)
            else:
                queryset = queryset.none()

        start_date = self.request.query_params.get('from_date')
        end_date = self.request.query_params.get('to_date')
        if start_date:
            queryset = queryset.filter(end_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(start_date__lte=end_date)

        return queryset
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def apply(self, request):
        """Apply for leave"""
        serializer = LeaveApplySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        employee = self.get_employee(request)
        if not employee:
            return Response(
                {'success': False, 'message': 'No employee profile found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        leave_type = data['leave_type_obj']
        total_days = data['calculated_total_days']
        
        # Check for overlapping leaves
        overlapping = LeaveRequest.objects.filter(
            organization=getattr(request, 'organization', None),
            employee=employee,
            status__in=[LeaveRequest.STATUS_PENDING, LeaveRequest.STATUS_APPROVED],
            start_date__lte=data['end_date'],
            end_date__gte=data['start_date']
        ).exists()
        
        if overlapping:
            return Response(
                {'success': False, 'message': 'You already have leave applied for these dates'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create leave request
        leave_request = LeaveRequest.objects.create(
                organization=getattr(request, 'organization', None),
            employee=employee,
            leave_type=leave_type,
            start_date=data['start_date'],
            end_date=data['end_date'],
            start_day_type=data.get('start_day_type', 'full'),
            end_day_type=data.get('end_day_type', 'full'),
            total_days=total_days,
            reason=data['reason'],
            contact_number=data.get('contact_number', ''),
            contact_address=data.get('contact_address', ''),
            attachment=data.get('attachment'),
                branch=getattr(employee, 'branch', None),
            created_by=request.user
        )
        
        # Submit for approval
        if leave_type.requires_approval:
            LeaveApprovalService.submit_for_approval(leave_request)
        else:
            # Auto-approve
            leave_request.status = LeaveRequest.STATUS_APPROVED
            leave_request.save()
            LeaveBalanceService.deduct_balance(
                employee, leave_type, total_days, data['start_date'].year
            )
        
        return Response({
            'success': True,
            'message': 'Leave applied successfully',
            'data': LeaveRequestDetailSerializer(leave_request).data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Approve or reject leave request"""
        leave_request = self.get_object()
        
        serializer = LeaveApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        if not hasattr(request.user, 'employee'):
            return Response({'error': 'No employee profile'}, status=400)
        
        approver = request.user.employee
        
        # Check if user is the current approver
        if leave_request.current_approver != approver:
            if not request.user.has_permission_for('leave.approve_any'):
                return Response(
                    {'error': 'You are not authorized to approve this request'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        action = serializer.validated_data['action']
        comments = serializer.validated_data.get('comments', '')
        
        if action == 'approve':
            LeaveApprovalService.approve(leave_request, approver, comments)
            message = 'Leave approved successfully'
        else:
            LeaveApprovalService.reject(leave_request, approver, comments)
            message = 'Leave rejected'
        
        return Response({
            'success': True,
            'message': message,
            'data': LeaveRequestDetailSerializer(leave_request).data
        })

    @action(detail=True, methods=['post'], url_path='reject')
    @transaction.atomic
    def reject(self, request, pk=None):
        """
        Compatibility alias for rejection.
        Accepts { reason } and maps to approve(action='reject').
        """
        leave_request = self.get_object()

        data = request.data.copy()
        data['action'] = 'reject'
        if 'comments' not in data and 'reason' in data:
            data['comments'] = data.get('reason', '')

        serializer = LeaveApproveSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        if not hasattr(request.user, 'employee'):
            return Response({'error': 'No employee profile'}, status=400)

        approver = request.user.employee

        if leave_request.current_approver != approver:
            if not request.user.has_permission_for('leave.approve_any'):
                return Response(
                    {'error': 'You are not authorized to approve this request'},
                    status=status.HTTP_403_FORBIDDEN
                )

        comments = serializer.validated_data.get('comments', '')
        LeaveApprovalService.reject(leave_request, approver, comments)

        return Response({
            'success': True,
            'message': 'Leave rejected',
            'data': LeaveRequestDetailSerializer(leave_request).data
        })
    
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """Cancel leave request"""
        leave_request = self.get_object()
        
        # Check ownership
        if not hasattr(request.user, 'employee'):
            return Response({'error': 'No employee profile'}, status=400)
        
        if leave_request.employee != request.user.employee:
            if not request.user.has_permission_for('leave.cancel_any'):
                return Response(
                    {'error': 'You can only cancel your own leave requests'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Check if can be cancelled
        if leave_request.status not in [LeaveRequest.STATUS_PENDING, LeaveRequest.STATUS_APPROVED]:
            return Response(
                {'error': 'This leave request cannot be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if leave has started
        if leave_request.status == LeaveRequest.STATUS_APPROVED:
            if leave_request.start_date <= timezone.now().date():
                return Response(
                    {'error': 'Cannot cancel leave that has already started'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        serializer = LeaveCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        LeaveApprovalService.cancel(
            leave_request,
            serializer.validated_data.get('reason', '')
        )
        
        return Response({
            'success': True,
            'message': 'Leave cancelled successfully'
        })
    
    @action(detail=False, methods=['get'])
    def my_requests(self, request):
        """Get current user's leave requests"""
        if not hasattr(request.user, 'employee'):
            return Response({'error': 'No employee profile'}, status=400)
        
        requests = LeaveRequest.objects.filter(
            employee=request.user.employee,
            is_active=True,
            organization=getattr(request, 'organization', None)
        ).select_related('leave_type').order_by('-created_at')
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            requests = requests.filter(status=status_filter)
        
        serializer = LeaveRequestListSerializer(requests, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_balance(self, request):
        """Get current user's leave balances"""
        employee = self.get_employee(request)
        if not employee:
            return Response({'error': 'No employee profile'}, status=400)
        
        year = request.query_params.get('year', timezone.now().year)
        balances = LeaveBalanceService.get_all_balances(
            employee, int(year)
        )
        
        serializer = LeaveBalanceSummarySerializer(balances, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def calculate(self, request):
        """Calculate leave days (preview before apply)"""
        serializer = LeaveCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        employee = request.user.employee if hasattr(request.user, 'employee') else None
        leave_policy = LeavePolicy.objects.filter(
            organization=getattr(request, 'organization', None),
            is_active=True
        ).order_by('-created_at').first()
        
        total_days, leave_dates = LeaveCalculationService.calculate_leave_days(
            data['start_date'],
            data['end_date'],
            data.get('start_day_type', 'full'),
            data.get('end_day_type', 'full'),
            leave_policy,
            employee
        )
        
        # Get excluded dates
        all_dates = set()
        current = data['start_date']
        while current <= data['end_date']:
            all_dates.add(current)
            current += timezone.timedelta(days=1)
        
        leave_dates_set = set(leave_dates)
        excluded = all_dates - leave_dates_set
        
        weekends = [d for d in excluded if d.weekday() >= 5]
        holidays_set = LeaveCalculationService._get_holidays(
            data['start_date'], data['end_date'], employee
        )
        holidays = [d for d in excluded if d in holidays_set]
        
        return Response({
            'total_days': total_days,
            'leave_dates': sorted(leave_dates),
            'weekends_excluded': sorted(weekends),
            'holidays_excluded': sorted(holidays)
        })
    
    @action(detail=False, methods=['get'])
    def pending_approvals(self, request):
        """Get pending approvals for current user"""
        employee = self.get_employee(request)
        if not employee:
            return Response({'error': 'No employee profile'}, status=400)
        
        pending = LeaveApprovalService.get_pending_approvals(
            employee,
            organization=getattr(request, 'organization', None)
        )
        serializer = LeaveRequestListSerializer(pending, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def team_leaves(self, request):
        """Get team leaves for calendar"""
        employee = self.get_employee(request)
        if not employee:
            return Response({'error': 'No employee profile'}, status=400)
        
        if not request.user.has_permission_for('leave.view_team'):
            return Response({'error': 'Permission denied'}, status=403)
        
        start_date = request.query_params.get('from_date')
        end_date = request.query_params.get('to_date')
        
        from datetime import datetime
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        leaves = LeaveApprovalService.get_team_leaves(
            manager=request.user.employee,
            start_date=start_date,
            end_date=end_date,
            organization=getattr(request, 'organization', None),
        )
        
        team_data = []
        for leave in leaves:
            team_data.append({
                'employee_id': leave.employee.employee_id,
                'employee_name': leave.employee.user.full_name,
                'avatar': leave.employee.user.avatar.url if leave.employee.user.avatar else None,
                'leave_type': leave.leave_type.name,
                'color': leave.leave_type.color,
                'start_date': leave.start_date,
                'end_date': leave.end_date,
                'status': leave.status,
            })
        
        serializer = TeamLeaveSerializer(team_data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='download-report')
    def download_report(self, request):
        """Download leave report as CSV"""
        import csv
        from django.http import HttpResponse
        from datetime import datetime
        
        if not request.user.has_permission_for('leave.view_reports'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Parse filters
        start_date = request.query_params.get('from_date')
        end_date = request.query_params.get('to_date')
        leave_status = request.query_params.get('status')
        leave_type_id = request.query_params.get('leave_type')
        employee_id = request.query_params.get('employee')
        
        queryset = self.get_queryset()
        
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(end_date__lte=end_date)
        if leave_status:
            queryset = queryset.filter(status=leave_status)
        if leave_type_id:
            queryset = queryset.filter(leave_type_id=leave_type_id)
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        
        # Generate CSV response
        response = HttpResponse(content_type='text/csv')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="leave_report_{timestamp}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Employee ID', 'Employee Name', 'Leave Type', 'Start Date', 'End Date',
            'Days', 'Status', 'Reason', 'Applied On'
        ])
        
        for leave in queryset:
            writer.writerow([
                leave.employee.employee_id,
                leave.employee.user.full_name,
                leave.leave_type.name,
                leave.start_date.strftime('%Y-%m-%d'),
                leave.end_date.strftime('%Y-%m-%d'),
                str(leave.total_days),
                leave.get_status_display(),
                leave.reason,
                leave.created_at.strftime('%Y-%m-%d %H:%M'),
            ])
        
        return response


class HolidayViewSet(BulkImportExportMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Holiday calendar management"""
    
    queryset = Holiday.objects.none()
    serializer_class = HolidaySerializer
    permission_classes = [IsAuthenticated, HasPermission, LeaveTenantPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = HolidayFilter
    search_fields = ['name']
    ordering_fields = ['date', 'name', 'created_at']
    ordering = ['date']
    
    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return Holiday.objects.none()
        return Holiday.objects.filter(
            organization=organization,
            is_active=True
        ).select_related('branch').prefetch_related('locations').order_by('date')

    def perform_create(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError('Organization context missing')
        serializer.save(organization=organization, created_by=self.request.user)

    def perform_update(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError('Organization context missing')
        serializer.save(organization=organization, updated_by=self.request.user)
    
    permission_map = {
        'list': ['leave.view'],
        'retrieve': ['leave.view'],
        'create': ['leave.manage_holidays'],
        'update': ['leave.manage_holidays'],
        'partial_update': ['leave.manage_holidays'],
        'destroy': ['leave.manage_holidays'],
    }
    
    def get_import_serializer_class(self):
        return HolidayBulkImportSerializer
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming holidays"""
        today = timezone.now().date()
        count = int(request.query_params.get('count', 5))
        
        holidays = self.get_queryset().filter(date__gte=today)[:count]
        serializer = self.get_serializer(holidays, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_year(self, request):
        """Get holidays for a year"""
        year = int(request.query_params.get('year', timezone.now().year))
        
        holidays = self.get_queryset().filter(
            date__year=year
        )
        
        serializer = self.get_serializer(holidays, many=True)
        return Response(serializer.data)


class LeaveEncashmentViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Leave encashment management
    
    SECURITY: Requires authentication and branch permission.
    Financial data - users can only view/manage their own encashments.
    """
    
    queryset = LeaveEncashment.objects.select_related('employee', 'employee__user', 'leave_type')
    serializer_class = LeaveEncashmentSerializer
    permission_classes = [IsAuthenticated, BranchPermission, LeaveTenantPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LeaveEncashmentFilter
    search_fields = ['employee__employee_id']
    ordering_fields = ['status', 'days_requested', 'created_at']
    ordering = ['-created_at']

    def get_employee(self, request):
        """Helper to get employee profile for current user"""
        if not hasattr(request, '_employee'):
            from apps.employees.models import Employee
            organization = getattr(request, 'organization', None)
            queryset = Employee.objects.filter(user=request.user)
            if organization:
                queryset = queryset.filter(organization=organization)
            request._employee = queryset.first()
        return request._employee
    
    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return LeaveEncashment.objects.none()
        queryset = LeaveEncashment.objects.filter(
            organization=organization
        ).select_related('employee', 'employee__user', 'leave_type')

        employee = self.get_employee(self.request)
        if employee and not self.request.user.has_permission_for('leave.approve_encashment'):
            queryset = queryset.filter(employee=employee)
        return queryset

    def perform_create(self, serializer):
        employee = self.get_employee(self.request)
        if not employee:
            raise ValidationError("No employee profile found for current user.")
        organization = getattr(self.request, 'organization', None)
        serializer.save(employee=employee, organization=organization, created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.status == LeaveEncashment.STATUS_PROCESSED:
            raise ValidationError('Processed encashments cannot be modified')
        organization = getattr(self.request, 'organization', None)
        serializer.save(organization=organization, updated_by=self.request.user)

    @action(detail=False, methods=['get'], url_path='my-encashments')
    def my_encashments(self, request):
        """Get current user's encashment requests"""
        employee = self.get_employee(request)
        if not employee:
            return Response({'error': 'No employee profile'}, status=400)
            
        encashments = LeaveEncashment.objects.filter(
            employee=employee,
            organization=getattr(request, 'organization', None)
        )
        serializer = self.get_serializer(encashments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Approve leave encashment request"""
        encashment = self.get_object()
        
        if encashment.status != LeaveEncashment.STATUS_PENDING:
            return Response(
                {'error': 'Only pending encashments can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not request.user.has_permission_for('leave.approve_encashment'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        approver = self.get_employee(request)
        if not approver:
            return Response({'error': 'No employee profile'}, status=400)
        
        days_approved = Decimal(str(request.data.get('days_approved', encashment.days_requested)))
        per_day_amount_input = request.data.get('per_day_amount')
        
        encashment.status = LeaveEncashment.STATUS_APPROVED
        encashment.days_approved = days_approved
        encashment.approved_by = approver
        encashment.approved_at = timezone.now()
        
        if per_day_amount_input:
            per_day_amount = Decimal(str(per_day_amount_input))
            encashment.per_day_amount = per_day_amount
            encashment.total_amount = per_day_amount * days_approved
        
        encashment.save()
        
        # Update leave balance - deduct encashed days
        LeaveBalanceService.get_or_create_balance(
            encashment.employee, encashment.leave_type, encashment.year
        )
        from .models import LeaveBalance
        balance = LeaveBalance.objects.get(
            employee=encashment.employee,
            leave_type=encashment.leave_type,
            year=encashment.year
        )
        balance.encashed += days_approved
        balance.save()
        
        serializer = self.get_serializer(encashment)
        return Response({
            'success': True,
            'message': 'Encashment approved successfully',
            'data': serializer.data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reject(self, request, pk=None):
        """Reject leave encashment request"""
        encashment = self.get_object()
        
        if encashment.status != LeaveEncashment.STATUS_PENDING:
            return Response(
                {'error': 'Only pending encashments can be rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not request.user.has_permission_for('leave.approve_encashment'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        approver = self.get_employee(request)
        if not approver:
            return Response({'error': 'No employee profile'}, status=400)
        
        encashment.status = LeaveEncashment.STATUS_REJECTED
        encashment.approved_by = approver
        encashment.approved_at = timezone.now()
        encashment.rejection_reason = request.data.get('reason', '')
        encashment.save()
        
        serializer = self.get_serializer(encashment)
        return Response({
            'success': True,
            'message': 'Encashment rejected',
            'data': serializer.data
        })


class CompensatoryLeaveViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Compensatory leave management
    
    SECURITY: Requires authentication and branch permission.
    """
    queryset = CompensatoryLeave.objects.select_related('employee', 'employee__user')
    serializer_class = CompensatoryLeaveSerializer
    permission_classes = [IsAuthenticated, BranchPermission, LeaveTenantPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CompensatoryLeaveFilter
    search_fields = ['employee__employee_id', 'reason']
    ordering_fields = ['status', 'work_date', 'created_at']
    ordering = ['-created_at']
    
    def get_employee(self, request):
        """Helper to get employee profile for current user"""
        if not hasattr(request, '_employee'):
            from apps.employees.models import Employee
            organization = getattr(request, 'organization', None)
            queryset = Employee.objects.filter(user=request.user)
            if organization:
                queryset = queryset.filter(organization=organization)
            request._employee = queryset.first()
        return request._employee
    
    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return CompensatoryLeave.objects.none()
        queryset = CompensatoryLeave.objects.filter(
            organization=organization
        ).select_related('employee', 'employee__user')

        employee = self.get_employee(self.request)
        if employee and not self.request.user.has_permission_for('leave.approve_compoff'):
            queryset = queryset.filter(employee=employee)
        return queryset
    
    def perform_create(self, serializer):
        employee = self.get_employee(self.request)
        if not employee:
            raise ValidationError("No employee profile found for current user.")
        organization = getattr(self.request, 'organization', None)
        serializer.save(employee=employee, organization=organization, created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.status == CompensatoryLeave.STATUS_USED:
            raise ValidationError('Used comp-off entries cannot be edited')
        organization = getattr(self.request, 'organization', None)
        serializer.save(organization=organization, updated_by=self.request.user)
        
    @action(detail=False, methods=['get'], url_path='my-compoffs')
    def my_compoffs(self, request):
        """Get current user's comp-off requests"""
        employee = self.get_employee(request)
        if not employee:
            return Response({'error': 'No employee profile'}, status=400)
            
        compoffs = CompensatoryLeave.objects.filter(
            employee=employee,
            organization=getattr(request, 'organization', None)
        )
        serializer = self.get_serializer(compoffs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Approve compensatory leave request"""
        from .models import CompensatoryLeave
        
        compoff = self.get_object()
        
        if compoff.status != CompensatoryLeave.STATUS_PENDING:
            return Response(
                {'error': 'Only pending comp-off requests can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not request.user.has_permission_for('leave.approve_compoff'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        approver = self.get_employee(request)
        if not approver:
            return Response({'error': 'No employee profile'}, status=400)
        
        days_credited = Decimal(str(request.data.get('days_credited', compoff.days_credited)))
        
        compoff.status = CompensatoryLeave.STATUS_APPROVED
        compoff.days_credited = days_credited
        compoff.approved_by = approver
        compoff.approved_at = timezone.now()
        
        # Set expiry date if not set (default: 90 days from approval)
        if not compoff.expiry_date:
            compoff.expiry_date = timezone.now().date() + timezone.timedelta(days=90)
        
        compoff.save()
        
        serializer = self.get_serializer(compoff)
        return Response({
            'success': True,
            'message': 'Comp-off approved successfully',
            'data': serializer.data
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reject(self, request, pk=None):
        """Reject compensatory leave request"""
        from .models import CompensatoryLeave
        
        compoff = self.get_object()
        
        if compoff.status != CompensatoryLeave.STATUS_PENDING:
            return Response(
                {'error': 'Only pending comp-off requests can be rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not request.user.has_permission_for('leave.approve_compoff'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        approver = self.get_employee(request)
        if not approver:
            return Response({'error': 'No employee profile'}, status=400)
        
        compoff.status = CompensatoryLeave.STATUS_REJECTED
        compoff.approved_by = approver
        compoff.approved_at = timezone.now()
        compoff.rejection_reason = request.data.get('reason', '')
        compoff.save()
        
        serializer = self.get_serializer(compoff)
        return Response({
            'success': True,
            'message': 'Comp-off rejected',
            'data': serializer.data
        })


class LeaveBalanceViewSet(OrganizationViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Leave Balance Management.
    - Admin: View all balances.
    - Manager: View team balances.
    - Employee: View own balances (filtered).
    """
    queryset = LeaveBalance.objects.select_related('employee', 'employee__user', 'leave_type')
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticated, LeaveTenantPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LeaveBalanceFilter
    ordering_fields = ['year', 'created_at']
    ordering = ['-year']
    search_fields = ['employee__employee_id', 'employee__user__first_name', 'employee__user__last_name']
    
    def get_queryset(self):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            return LeaveBalance.objects.none()

        queryset = LeaveBalance.objects.filter(
            organization=organization
        ).select_related('employee', 'employee__user', 'leave_type')

        user = self.request.user
        if user.has_permission_for('leave.view_all_balances'):
            return queryset

        if hasattr(user, 'employee') and user.has_permission_for('leave.view_team_balances'):
            team_ids = list(user.employee.direct_reports.values_list('id', flat=True))
            team_ids.append(user.employee.id)
            return queryset.filter(employee_id__in=team_ids)

        if hasattr(user, 'employee'):
            return queryset.filter(employee=user.employee)

        return queryset.none()

    @action(detail=False, methods=['post'], url_path='process-carry-forward')
    @transaction.atomic
    def process_carry_forward(self, request):
        """Process year-end carry forward for all employees"""
        if not request.user.has_permission_for('leave.manage_balances'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from_year = request.data.get('from_year', timezone.now().year - 1)
        to_year = request.data.get('to_year', timezone.now().year)
        
        if to_year <= from_year:
            return Response(
                {'error': 'to_year must be greater than from_year'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            LeaveBalanceService.run_year_end_carryforward(
                from_year,
                to_year,
                organization=getattr(request, 'organization', None)
            )
            
            # Get count of processed balances
            processed_count = LeaveBalance.objects.filter(
                year=to_year,
                carry_forward__gt=0
            ).count()
            
            return Response({
                'success': True,
                'message': f'Carry forward processed from {from_year} to {to_year}',
                'balances_processed': processed_count
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='process-accrual')
    @transaction.atomic
    def process_accrual(self, request):
        """Process monthly leave accrual for all employees"""
        if not request.user.has_permission_for('leave.manage_balances'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        accrual_type = request.data.get('accrual_type', 'monthly')
        
        try:
            if accrual_type == 'monthly':
                LeaveBalanceService.run_monthly_accrual(
                    organization=getattr(request, 'organization', None)
                )
            else:
                return Response(
                    {'error': f'Unsupported accrual type: {accrual_type}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            return Response({
                'success': True,
                'message': f'{accrual_type.capitalize()} accrual processed successfully',
                'processed_at': timezone.now().isoformat()
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
