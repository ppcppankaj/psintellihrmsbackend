"""
Asset Management Views
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.core.tenant_guards import OrganizationViewSetMixin
from apps.core.mixins import BulkImportExportMixin
from apps.core.permissions_branch import BranchFilterBackend, BranchPermission
from .permissions import AssetsTenantPermission
from apps.abac.permissions import ABACPermission

from .models import AssetCategory, Asset, AssetAssignment, AssetMaintenance, AssetRequest
from .serializers import (
    AssetCategorySerializer,
    AssetSerializer,
    AssetListSerializer,
    AssetDetailSerializer,
    AssetAssignmentSerializer,
    AssignAssetSerializer,
    UnassignAssetSerializer,
    AssetBulkImportSerializer,
    AssetMaintenanceSerializer,
    AssetRequestSerializer,
    AssetRequestCreateSerializer,
    AssetRequestReviewSerializer,
    AssetRequestFulfillSerializer,
)
from .filters import AssetCategoryFilter, AssetFilter, AssetAssignmentFilter, AssetMaintenanceFilter, AssetRequestFilter


class AssetCategoryViewSet(BulkImportExportMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for asset categories"""
    
    queryset = AssetCategory.objects.none()
    serializer_class = AssetCategorySerializer
    permission_classes = [IsAuthenticated, AssetsTenantPermission]
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AssetCategoryFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'created_at']


class AssetViewSet(BulkImportExportMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing assets"""
    
    queryset = Asset.objects.none()
    permission_classes = [IsAuthenticated, AssetsTenantPermission, BranchPermission]
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False).select_related('category', 'current_assignee')
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AssetFilter
    search_fields = ['name', 'asset_tag', 'serial_number']
    ordering_fields = ['name', 'asset_tag', 'purchase_date', 'created_at']
    
    def get_import_serializer_class(self):
        return AssetBulkImportSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return AssetListSerializer
        elif self.action == 'retrieve':
            return AssetDetailSerializer
        return AssetSerializer
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign asset to an employee"""
        asset = self.get_object()
        
        if asset.status == Asset.ASSIGNED:
            return Response(
                {'success': False, 'message': 'Asset is already assigned'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = AssignAssetSerializer(data=request.data)
        if serializer.is_valid():
            from apps.employees.models import Employee
            try:
                employee = Employee.objects.get(id=serializer.validated_data['employee_id'])
            except Employee.DoesNotExist:
                return Response(
                    {'success': False, 'message': 'Employee not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            assignment = asset.assign_to(
                employee=employee,
                assigned_by=request.user,
                notes=serializer.validated_data.get('notes', '')
            )
            
            return Response({
                'success': True,
                'message': f'Asset assigned to {employee.full_name}',
                'data': AssetAssignmentSerializer(assignment).data
            })
        
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def unassign(self, request, pk=None):
        """Return asset from current assignee"""
        asset = self.get_object()
        
        if not asset.current_assignee:
            return Response(
                {'success': False, 'message': 'Asset is not currently assigned'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = UnassignAssetSerializer(data=request.data)
        if serializer.is_valid():
            assignee_name = asset.current_assignee.full_name
            asset.unassign(
                returned_by=request.user,
                notes=serializer.validated_data.get('notes', '')
            )
            
            return Response({
                'success': True,
                'message': f'Asset returned from {assignee_name}'
            })
        
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='return')
    def return_asset(self, request, pk=None):
        """
        Compatibility alias for returning assets.
        Mirrors /{id}/unassign/ behavior to avoid breaking older clients.
        """
        return self.unassign(request, pk=pk)

    @action(detail=True, methods=['post'], url_path='maintenance')
    def send_to_maintenance(self, request, pk=None):
        """
        Compatibility alias for creating a maintenance record.
        Frontend sends notes only; we create a minimal scheduled maintenance entry.
        """
        asset = self.get_object()

        title = request.data.get('title') or f"Maintenance for {asset.asset_tag}"
        notes = request.data.get('notes', '')
        maintenance_type = request.data.get('maintenance_type', AssetMaintenance.CORRECTIVE)

        maintenance = AssetMaintenance.objects.create(
            asset=asset,
            maintenance_type=maintenance_type,
            status=AssetMaintenance.SCHEDULED,
            title=title,
            description=notes,
            scheduled_date=timezone.now().date(),
            performed_by=request.user,
            notes=notes,
        )

        if asset.status != Asset.MAINTENANCE:
            asset.status = Asset.MAINTENANCE
            asset.save(update_fields=['status'])

        return Response({
            'success': True,
            'message': 'Maintenance scheduled',
            'data': AssetMaintenanceSerializer(maintenance).data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get asset statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'available': queryset.filter(status=Asset.AVAILABLE).count(),
            'assigned': queryset.filter(status=Asset.ASSIGNED).count(),
            'maintenance': queryset.filter(status=Asset.MAINTENANCE).count(),
            'retired': queryset.filter(status=Asset.RETIRED).count(),
        }
        
        # By category
        from django.db.models import Count
        by_category = queryset.values('category__name').annotate(count=Count('id'))
        stats['by_category'] = list(by_category)
        
        return Response({'success': True, 'data': stats})
    
    @action(detail=True, methods=['get'])
    def calculate_depreciation(self, request, pk=None):
        """Calculate depreciation for an asset using straight-line method"""
        asset = self.get_object()
        
        if not asset.purchase_price or not asset.purchase_date:
            return Response(
                {'success': False, 'message': 'Asset must have purchase price and date for depreciation calculation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.utils import timezone
        from decimal import Decimal
        
        depreciation_rate = Decimal(request.query_params.get('rate', '20'))
        method = request.query_params.get('method', 'straight_line')
        
        today = timezone.now().date()
        days_owned = (today - asset.purchase_date).days
        years_owned = Decimal(days_owned) / Decimal('365')
        
        if method == 'straight_line':
            annual_depreciation = asset.purchase_price * (depreciation_rate / Decimal('100'))
            total_depreciation = annual_depreciation * years_owned
            current_value = max(asset.purchase_price - total_depreciation, Decimal('0'))
        else:
            current_value = asset.purchase_price * ((Decimal('1') - depreciation_rate / Decimal('100')) ** years_owned)
            total_depreciation = asset.purchase_price - current_value
        
        return Response({
            'success': True,
            'data': {
                'asset_id': str(asset.id),
                'asset_name': asset.name,
                'purchase_price': str(asset.purchase_price),
                'purchase_date': str(asset.purchase_date),
                'current_value': str(round(current_value, 2)),
                'depreciation_amount': str(round(total_depreciation, 2)),
                'depreciation_rate': str(depreciation_rate),
                'years_owned': str(round(years_owned, 2)),
                'method': method
            }
        })


class AssetAssignmentViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for asset assignments (history)"""
    
    queryset = AssetAssignment.objects.none()
    serializer_class = AssetAssignmentSerializer
    permission_classes = [IsAuthenticated, AssetsTenantPermission]
    
    def get_queryset(self):
        return super().get_queryset().select_related('asset', 'employee', 'assigned_by')
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AssetAssignmentFilter
    ordering_fields = ['assigned_date', 'returned_date']


class AssetMaintenanceViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for asset maintenance tracking"""
    
    queryset = AssetMaintenance.objects.none()
    serializer_class = AssetMaintenanceSerializer
    permission_classes = [IsAuthenticated, AssetsTenantPermission]
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False).select_related('asset', 'performed_by')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AssetMaintenanceFilter
    search_fields = ['title', 'description', 'asset__asset_tag']
    ordering_fields = ['scheduled_date', 'completed_date', 'created_at']
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark maintenance as completed"""
        maintenance = self.get_object()
        
        if maintenance.status == AssetMaintenance.COMPLETED:
            return Response(
                {'success': False, 'message': 'Maintenance is already completed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.utils import timezone
        maintenance.status = AssetMaintenance.COMPLETED
        maintenance.completed_date = timezone.now().date()
        maintenance.performed_by = request.user
        maintenance.save()
        
        if maintenance.asset.status == Asset.MAINTENANCE:
            maintenance.asset.status = Asset.AVAILABLE
            maintenance.asset.save()
        
        return Response({
            'success': True,
            'message': 'Maintenance completed',
            'data': AssetMaintenanceSerializer(maintenance).data
        })
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming scheduled maintenance"""
        from django.utils import timezone
        today = timezone.now().date()
        upcoming = self.get_queryset().filter(
            status=AssetMaintenance.SCHEDULED,
            scheduled_date__gte=today
        ).order_by('scheduled_date')[:10]
        
        return Response({
            'success': True,
            'data': AssetMaintenanceSerializer(upcoming, many=True).data
        })
    
    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get overdue maintenance"""
        from django.utils import timezone
        today = timezone.now().date()
        overdue = self.get_queryset().filter(
            status__in=[AssetMaintenance.SCHEDULED, AssetMaintenance.IN_PROGRESS],
            scheduled_date__lt=today
        ).order_by('scheduled_date')
        
        return Response({
            'success': True,
            'data': AssetMaintenanceSerializer(overdue, many=True).data
        })


class AssetRequestViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for employee asset requests"""
    
    queryset = AssetRequest.objects.none()
    serializer_class = AssetRequestSerializer
    permission_classes = [IsAuthenticated, AssetsTenantPermission]
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False).select_related('employee', 'category', 'reviewed_by', 'fulfilled_asset')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AssetRequestFilter
    search_fields = ['title', 'description']
    ordering_fields = ['requested_date', 'needed_by', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AssetRequestCreateSerializer
        return AssetRequestSerializer
    
    def perform_create(self, serializer):
        from apps.employees.models import Employee
        try:
            employee = Employee.objects.get(user=self.request.user)
            serializer.save(employee=employee)
        except Employee.DoesNotExist:
            raise serializers.ValidationError({'employee': 'Current user is not linked to an employee record'})
    
    @action(detail=False, methods=['get'])
    def my_requests(self, request):
        """Get current user's asset requests"""
        from apps.employees.models import Employee
        try:
            employee = Employee.objects.get(user=request.user)
            requests = self.get_queryset().filter(employee=employee)
            return Response({
                'success': True,
                'data': AssetRequestSerializer(requests, many=True).data
            })
        except Employee.DoesNotExist:
            return Response({
                'success': False,
                'message': 'User is not linked to an employee record'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Approve or reject an asset request"""
        asset_request = self.get_object()
        
        if asset_request.status != AssetRequest.PENDING:
            return Response(
                {'success': False, 'message': 'Only pending requests can be reviewed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = AssetRequestReviewSerializer(data=request.data)
        if serializer.is_valid():
            action_type = serializer.validated_data['action']
            notes = serializer.validated_data.get('notes', '')
            
            if action_type == 'approve':
                asset_request.approve(request.user, notes)
                message = 'Request approved'
            else:
                asset_request.reject(request.user, notes)
                message = 'Request rejected'
            
            return Response({
                'success': True,
                'message': message,
                'data': AssetRequestSerializer(asset_request).data
            })
        
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        """Fulfill an approved request by assigning an asset"""
        asset_request = self.get_object()
        
        if asset_request.status != AssetRequest.APPROVED:
            return Response(
                {'success': False, 'message': 'Only approved requests can be fulfilled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = AssetRequestFulfillSerializer(data=request.data)
        if serializer.is_valid():
            try:
                asset = Asset.objects.get(id=serializer.validated_data['asset_id'])
            except Asset.DoesNotExist:
                return Response(
                    {'success': False, 'message': 'Asset not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if asset.status != Asset.AVAILABLE:
                return Response(
                    {'success': False, 'message': 'Asset is not available for assignment'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            asset.assign_to(asset_request.employee, assigned_by=request.user, notes=f'Fulfilled request: {asset_request.title}')
            asset_request.fulfill(asset, request.user)
            
            return Response({
                'success': True,
                'message': f'Request fulfilled with asset {asset.asset_tag}',
                'data': AssetRequestSerializer(asset_request).data
            })
        
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get all pending requests (for managers/admins)"""
        pending = self.get_queryset().filter(status=AssetRequest.PENDING)
        return Response({
            'success': True,
            'data': AssetRequestSerializer(pending, many=True).data
        })
