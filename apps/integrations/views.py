"""Integration ViewSets

SECURITY: All integration management endpoints require superuser access.
These endpoints expose sensitive system configuration (API keys, webhooks).
"""
from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
import secrets
import requests
from rest_framework.exceptions import PermissionDenied
from .models import Integration, Webhook, APIKey
from .serializers import IntegrationSerializer, WebhookSerializer, APIKeySerializer
from apps.core.tenant_guards import OrganizationViewSetMixin
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .filters import IntegrationFilter, WebhookFilter, APIKeyFilter


class IsSuperuserOnly(permissions.BasePermission):
    """Only allow superusers to access these endpoints."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser


class IntegrationViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Integration management - Superuser only"""
    queryset = Integration.objects.none()
    serializer_class = IntegrationSerializer
    permission_classes = [IsSuperuserOnly]
    
    def get_queryset(self):
        return super().get_queryset()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = IntegrationFilter

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)

    @action(detail=True, methods=['post'])
    def connect(self, request, pk=None):
        integration = self.get_object()
        integration.is_connected = True
        integration.last_sync = timezone.now()
        if 'config' in request.data:
            integration.config = request.data.get('config', integration.config)
        if 'credentials' in request.data:
            integration.credentials = request.data.get('credentials', integration.credentials)
        integration.save()
        return Response({'success': True, 'data': self.get_serializer(integration).data})

    @action(detail=True, methods=['post'])
    def disconnect(self, request, pk=None):
        integration = self.get_object()
        integration.is_connected = False
        integration.save(update_fields=['is_connected'])
        return Response({'success': True, 'data': self.get_serializer(integration).data})

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        integration = self.get_object()
        integration.last_sync = timezone.now()
        integration.save(update_fields=['last_sync'])
        return Response({'success': True, 'message': 'Sync queued', 'data': self.get_serializer(integration).data})


class WebhookViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Webhook management - Superuser only"""
    queryset = Webhook.objects.none()
    serializer_class = WebhookSerializer
    permission_classes = [IsSuperuserOnly]
    
    def get_queryset(self):
        return super().get_queryset()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = WebhookFilter

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        webhook = self.get_object()
        if not webhook.is_active:
            return Response({'success': False, 'message': 'Webhook is inactive'}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'event': request.data.get('event', 'webhook.test'),
            'timestamp': timezone.now().isoformat(),
            'data': request.data.get('data', {'message': 'Test payload'}),
        }
        headers = webhook.headers or {}
        if webhook.secret:
            headers['X-Webhook-Secret'] = webhook.secret

        try:
            resp = requests.post(webhook.url, json=payload, headers=headers, timeout=5)
            return Response({'success': True, 'status_code': resp.status_code})
        except Exception as exc:
            return Response({'success': False, 'message': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def rotate_secret(self, request, pk=None):
        webhook = self.get_object()
        webhook.secret = secrets.token_urlsafe(32)
        webhook.save(update_fields=['secret'])
        return Response({'success': True, 'data': self.get_serializer(webhook).data})


class APIKeyViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """API Key management - Superuser only"""
    queryset = APIKey.objects.none()
    serializer_class = APIKeySerializer
    permission_classes = [IsSuperuserOnly]
    
    def get_queryset(self):
        return super().get_queryset()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = APIKeyFilter

    def perform_create(self, serializer):
        key = secrets.token_hex(32)
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(key=key, organization=org)

    @action(detail=True, methods=['post'])
    def rotate(self, request, pk=None):
        api_key = self.get_object()
        api_key.key = secrets.token_hex(32)
        api_key.save(update_fields=['key'])
        return Response({'success': True, 'data': self.get_serializer(api_key).data})
