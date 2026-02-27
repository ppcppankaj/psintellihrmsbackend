"""Notification ViewSets"""

from rest_framework import mixins, permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.tenant_guards import OrganizationViewSetMixin

from .models import Notification, NotificationPreference, NotificationTemplate
from .permissions import IsNotificationAdmin, IsNotificationManager, NotificationsTenantPermission
from .filters import NotificationFilter, NotificationTemplateFilter, NotificationPreferenceFilter
from .serializers import (
    NotificationDispatchSerializer,
    NotificationPreferenceSerializer,
    NotificationReadSerializer,
    NotificationSerializer,
    NotificationTemplateSerializer,
    PushNotificationSerializer,
    SendDigestSerializer,
)
from .services import NotificationService


class NotificationViewSet(OrganizationViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated, NotificationsTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = NotificationFilter
    search_fields = ['title', 'message']
    ordering_fields = ['is_read', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        base_qs = super().get_queryset()
        return base_qs.filter(recipient__user=self.request.user).select_related('template', 'recipient').order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='read')
    def mark_read(self, request, pk=None):
        serializer = NotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = NotificationService.mark_as_read(pk, request.user)
        if not updated:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'read'})

    @action(detail=False, methods=['post'], url_path='read-all')
    def mark_all_read(self, request):
        updated = NotificationService.mark_all_as_read(request.user)
        return Response({'updated': updated})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'unread_count': NotificationService.unread_count(request.user)})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNotificationManager], url_path='bulk-send')
    def bulk_send(self, request):
        serializer = NotificationDispatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_id = getattr(request.user, 'organization_id', None)
        if not organization_id:
            return Response({'detail': 'Organization context required'}, status=status.HTTP_400_BAD_REQUEST)
        result = NotificationService.bulk_notify(organization_id=str(organization_id), **serializer.validated_data)
        return Response(result, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNotificationManager], url_path='push')
    def push_notification(self, request):
        serializer = PushNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_id = getattr(request.user, 'organization_id', None)
        if not organization_id:
            return Response({'detail': 'Organization context required'}, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        result = NotificationService.send_push_notifications(
            organization_id=str(organization_id),
            recipient_ids=data['recipient_ids'],
            title=data['title'],
            body=data['body'],
            data=data.get('data'),
            priority=data.get('priority', 'normal'),
        )
        return Response(result, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsNotificationManager], url_path='send-digest')
    def send_digest(self, request):
        serializer = SendDigestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_id = getattr(request.user, 'organization_id', None)
        if not organization_id:
            return Response({'detail': 'Organization context required'}, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        result = NotificationService.send_digest(
            organization_id=str(organization_id),
            digest_type=data['digest_type'],
            user_ids=data.get('recipient_ids'),
        )
        return Response(result)


class NotificationTemplateViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, NotificationsTenantPermission, IsNotificationAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = NotificationTemplateFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        return super().get_queryset().order_by('name')

    def perform_create(self, serializer):
        organization = getattr(self.request.user, 'organization', None)
        serializer.save(organization=organization)

    def perform_update(self, serializer):
        organization = getattr(self.request.user, 'organization', None)
        serializer.save(organization=organization)


class NotificationPreferenceViewSet(
    OrganizationViewSetMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = NotificationPreference.objects.all()
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated, NotificationsTenantPermission]

    def get_object(self):
        preference, _ = NotificationPreference.objects.get_or_create(
            user=self.request.user,
            defaults={'organization': getattr(self.request.user, 'organization', None)},
        )
        return preference

    def list(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'put', 'patch'])
    def me(self, request):
        instance = self.get_object()
        if request.method == 'GET':
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        serializer = self.get_serializer(instance, data=request.data, partial=request.method == 'PATCH')
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
