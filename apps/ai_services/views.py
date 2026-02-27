"""AI ViewSets

SECURITY:
- AIModelVersionViewSet: Superuser only (manages ML models)
- AIPredictionViewSet: Authenticated users (read), Superuser (write)
"""
from django.apps import apps
from django.utils import timezone
from rest_framework import permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import AIPrediction, AIModelVersion
from .serializers import (
    AIInferenceRequestSerializer,
    AIModelVersionSerializer,
    AIPredictionSerializer,
)
from .filters import AIModelVersionFilter, AIPredictionFilter
from .services import AIPredictionService
from .tasks import run_ai_prediction_task
from apps.core.tenant_guards import OrganizationViewSetMixin
from .permissions import AIServicesTenantPermission


class IsSuperuserOnly(permissions.BasePermission):
    """Only allow superusers to access these endpoints."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser


class IsSuperuserOrReadOnly(permissions.BasePermission):
    """Allow read for authenticated users, write only for superusers."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_superuser


class AIModelVersionViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """AI Model Version management - Superuser only"""
    queryset = AIModelVersion.objects.all()
    serializer_class = AIModelVersionSerializer
    permission_classes = [IsSuperuserOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AIModelVersionFilter
    search_fields = ['model_type']
    ordering_fields = ['model_type', 'is_active', 'created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        organization = serializer.validated_data.get('organization')
        if not organization:
            organization = self.request.user.get_organization()
        if not organization:
            raise PermissionDenied("organization is required")
        serializer.save(organization=organization, created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def predict(self, request, pk=None):
        """Generate a stub prediction for an entity"""
        model_version = self.get_object()
        user_org = request.user.get_organization() if not request.user.is_superuser else None
        entity_type = request.data.get('entity_type')
        entity_id = request.data.get('entity_id')
        if not entity_type or not entity_id:
            return Response({'success': False, 'message': 'entity_type and entity_id required'}, status=status.HTTP_400_BAD_REQUEST)

        if user_org and model_version.organization_id != user_org.id:
            return Response({'success': False, 'message': 'Cross-organization model access denied'}, status=status.HTTP_403_FORBIDDEN)

        prediction = {
            'model_version': str(model_version.id),
            'entity_type': entity_type,
            'entity_id': entity_id,
            'score': request.data.get('score', 0.5),
            'timestamp': timezone.now().isoformat(),
        }
        aip = AIPrediction.objects.create(
            model_version=model_version,
            entity_type=entity_type,
            entity_id=entity_id,
            prediction=prediction,
            confidence=request.data.get('confidence', 0.5),
            reviewed_by=getattr(request.user, 'employee', None),
            organization=user_org or model_version.organization,
            created_by=request.user
        )
        return Response({'success': True, 'data': AIPredictionSerializer(aip).data}, status=status.HTTP_201_CREATED)


class AIPredictionViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """AI Predictions - Read for authenticated, Write for superuser"""
    queryset = AIPrediction.objects.all()
    serializer_class = AIPredictionSerializer
    permission_classes = [IsSuperuserOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AIPredictionFilter
    search_fields = ['entity_type']
    ordering_fields = ['entity_type', 'confidence', 'human_reviewed', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return super().get_queryset().select_related('model_version', 'reviewed_by')

    def perform_create(self, serializer):
        model_version = serializer.validated_data.get('model_version')

        if self.request.user.is_superuser:
            organization = serializer.validated_data.get('organization')
            if not organization and model_version:
                organization = model_version.organization
            if not organization:
                organization = self.request.user.get_organization()
            if not organization:
                raise PermissionDenied("organization is required")
            if model_version and model_version.organization_id != organization.id:
                raise PermissionDenied("Model version belongs to a different organization")
            serializer.save(organization=organization, created_by=self.request.user)
            return

        org = self.request.user.get_organization()
        if not org:
            raise PermissionDenied("Organization context required")
        serializer.save(organization=org, created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        prediction = self.get_object()
        prediction.human_reviewed = True
        prediction.reviewed_by = getattr(request.user, 'employee', None)
        prediction.updated_by = request.user
        prediction.save(update_fields=['human_reviewed', 'reviewed_by', 'updated_by', 'updated_at'])
        return Response({'success': True, 'data': self.get_serializer(prediction).data})

    @action(detail=True, methods=['post'])
    def override(self, request, pk=None):
        prediction = self.get_object()
        prediction.human_reviewed = True
        prediction.human_override = request.data.get('override', {})
        prediction.reviewed_by = getattr(request.user, 'employee', None)
        prediction.updated_by = request.user
        prediction.save(update_fields=['human_reviewed', 'human_override', 'reviewed_by', 'updated_by', 'updated_at'])
        return Response({'success': True, 'data': self.get_serializer(prediction).data})


class AIInferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated, AIServicesTenantPermission]

    def post(self, request):
        serializer = AIInferenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = self._resolve_organization(request, data.get('organization_id'))

        if data.get('async_mode'):
            task = run_ai_prediction_task.delay(
                str(organization.id),
                data['model_type'],
                data['entity_type'],
                str(data['entity_id']),
                data['input_data'],
            )
            return Response(
                {
                    'success': True,
                    'task_id': task.id,
                    'message': 'Prediction enqueued for async execution.',
                },
                status=status.HTTP_202_ACCEPTED,
            )

        prediction = AIPredictionService.run_prediction(
            organization=organization,
            model_type=data['model_type'],
            entity_type=data['entity_type'],
            entity_id=str(data['entity_id']),
            input_data=data['input_data'],
        )
        return Response(
            {
                'success': True,
                'data': AIPredictionSerializer(prediction).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _resolve_organization(self, request, organization_id):
        Organization = apps.get_model('core', 'Organization')
        if organization_id:
            organization = Organization.objects.filter(id=organization_id).first()
            if not organization:
                raise PermissionDenied('Organization not found.')
            if not request.user.is_superuser:
                user_org = request.user.get_organization()
                if not user_org or user_org.id != organization.id:
                    raise PermissionDenied('Cross-organization access denied.')
            return organization

        organization = request.user.get_organization()
        if not organization:
            raise PermissionDenied('Organization context required.')
        return organization
