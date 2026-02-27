"""
Chat Views - REST API endpoints for chat functionality
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Max
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django_filters.rest_framework import DjangoFilterBackend
import logging

from apps.core.tenant_guards import OrganizationViewSetMixin

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReaction,
    MeetingRoom,
    MeetingRecording,
    MeetingSchedule,
)
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    MessageSerializer, CreateDirectConversationSerializer,
    CreateGroupConversationSerializer, SendMessageSerializer,
    MeetingRoomSerializer, MeetingScheduleSerializer,
    MeetingRecordingSerializer, MeetingRecordingUploadSerializer,
)
from .filters import (
    ConversationFilter, MessageFilter,
    MeetingRoomFilter, MeetingScheduleFilter, MeetingRecordingFilter,
)
from .permissions import ChatTenantPermission, IsConversationParticipant, CanManageMeetings
from .utils import build_meeting_url


logger = logging.getLogger(__name__)


class ConversationViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    API endpoint for managing conversations.
    Users can only see conversations they are a participant of.
    """
    serializer_class = ConversationListSerializer
    permission_classes = [IsAuthenticated, ChatTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ConversationFilter
    search_fields = ['name']
    ordering_fields = ['last_message_at', 'created_at']
    ordering = ['-last_message_at']

    def _get_user_org(self):
        if self.request.user.is_superuser:
            return None
        return self.request.user.get_organization()
    
    def get_queryset(self):
        user = self.request.user
        queryset = Conversation.objects.filter(
            participants__user=user,
            participants__is_archived=False,
            is_deleted=False
        ).prefetch_related(
            'participants__user',
            'messages',
        ).select_related('organization')

        if not user.is_superuser:
            user_org = self._get_user_org()
            if not user_org:
                return queryset.none()
            queryset = queryset.filter(organization=user_org)

        return queryset.annotate(
            latest_message=Max('messages__created_at')
        ).order_by('-latest_message')
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationListSerializer
    
    @action(detail=False, methods=['post'], url_path='start-direct')
    def start_direct(self, request):
        """Start or get existing 1:1 conversation with another user"""
        serializer = CreateDirectConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        target_user_id = serializer.validated_data['user_id']
        current_user = request.user
        current_user_org = current_user.get_organization() if not current_user.is_superuser else None
        if not current_user.is_superuser and not current_user_org:
            return Response({'error': 'Organization context required'}, status=status.HTTP_403_FORBIDDEN)
        
        # Look up the target user - could be User ID or Employee ID
        from django.contrib.auth import get_user_model
        from apps.employees.models import Employee
        User = get_user_model()
        
        target_user = None
        # First try as User ID
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            # Try as Employee ID - get the linked user
            try:
                employee = Employee.objects.get(id=target_user_id)
                target_user = employee.user
            except Employee.DoesNotExist:
                pass
        
        if not target_user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if not current_user.is_superuser:
            target_user_org = target_user.get_organization()
            if not target_user_org or target_user_org.id != current_user_org.id:
                return Response(
                    {'error': 'Cannot start conversation across organizations'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Check for existing direct conversation
        existing = self.get_queryset().filter(
            type=Conversation.Type.DIRECT,
            participants__user=current_user
        ).filter(
            participants__user=target_user
        ).first()
        
        if existing:
            return Response(ConversationDetailSerializer(existing).data)
        
        # Create new direct conversation
        conversation_org = current_user_org or target_user.get_organization()
        if not conversation_org:
            return Response({'error': 'Target user has no organization'}, status=status.HTTP_400_BAD_REQUEST)

        conversation = Conversation.objects.create(
            type=Conversation.Type.DIRECT,
            organization=conversation_org,
            created_by=current_user,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=current_user,
            role=ConversationParticipant.Role.MEMBER,
            organization=conversation.organization,
            created_by=current_user,
        )
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=target_user,
            role=ConversationParticipant.Role.MEMBER,
            organization=conversation.organization,
            created_by=current_user,
        )
        
        # Send initial message if provided
        initial_message = serializer.validated_data.get('initial_message')
        if initial_message:
            Message.objects.create(
                conversation=conversation,
                sender=current_user,
                content=initial_message,
                organization=conversation.organization,
                created_by=current_user,
            )
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['last_message_at', 'updated_at'])
        
        return Response(ConversationDetailSerializer(conversation).data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], url_path='create-group')
    def create_group(self, request):
        """Create a new group chat"""
        serializer = CreateGroupConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        current_user = request.user
        current_user_org = current_user.get_organization() if not current_user.is_superuser else None
        if not current_user.is_superuser and not current_user_org:
            return Response({'error': 'Organization context required'}, status=status.HTTP_403_FORBIDDEN)

        conversation_org = current_user_org
        if not conversation_org:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            first_member_id = serializer.validated_data['user_ids'][0]
            first_member = User.objects.filter(id=first_member_id).first()
            conversation_org = first_member.get_organization() if first_member else None

        if not conversation_org:
            return Response({'error': 'Unable to resolve organization for group'}, status=status.HTTP_400_BAD_REQUEST)

        conversation = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            name=serializer.validated_data['name'],
            description=serializer.validated_data.get('description', ''),
            organization=conversation_org,
            created_by=current_user,
        )
        
        # Add creator as admin
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=current_user,
            role=ConversationParticipant.Role.ADMIN,
            organization=conversation.organization,
            created_by=current_user,
        )
        
        # Add other members
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for user_id in serializer.validated_data['user_ids']:
            try:
                user = User.objects.get(id=user_id)
                user_org = user.get_organization()
                if not user_org or user_org.id != conversation_org.id:
                    if not current_user.is_superuser:
                        continue
                    continue
                ConversationParticipant.objects.get_or_create(
                    conversation=conversation, user=user,
                    defaults={
                        'role': ConversationParticipant.Role.MEMBER,
                        'organization': conversation.organization,
                        'created_by': current_user,
                    }
                )
            except User.DoesNotExist:
                pass # Skip invalid user IDs
        
        return Response(ConversationDetailSerializer(conversation).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark all messages in conversation as read"""
        conversation = self.get_object()
        participant = ConversationParticipant.objects.filter(
            conversation=conversation, user=request.user
        ).first()
        
        if participant:
            participant.last_read_at = timezone.now()
            participant.save()
            return Response({'status': 'marked as read'})
        return Response({'error': 'Not a participant'}, status=status.HTTP_403_FORBIDDEN)
    
    @action(detail=True, methods=['post'])
    def mute(self, request, pk=None):
        """Mute/unmute a conversation"""
        conversation = self.get_object()
        participant = ConversationParticipant.objects.filter(
            conversation=conversation, user=request.user
        ).first()
        
        if participant:
            participant.is_muted = not participant.is_muted
            participant.save()
            return Response({'is_muted': participant.is_muted})
        return Response({'error': 'Not a participant'}, status=status.HTTP_403_FORBIDDEN)


class MessageViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    API endpoint for messages within a conversation.
    """
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated, ChatTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MessageFilter
    search_fields = ['content']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def _get_user_org(self):
        if self.request.user.is_superuser:
            return None
        return self.request.user.get_organization()

    def list(self, request, *args, **kwargs):
        """Validate conversation + participant before listing messages"""
        conversation_id = request.query_params.get('conversation')
        if not conversation_id:
            return Response({'error': 'conversation parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        conversation_qs = Conversation.objects.filter(id=conversation_id)
        user_org = self._get_user_org()
        if not request.user.is_superuser:
            if not user_org:
                return Response({'error': 'Organization context required'}, status=status.HTTP_403_FORBIDDEN)
            conversation_qs = conversation_qs.filter(organization=user_org)

        conversation = conversation_qs.first()
        if not conversation:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

        is_participant = ConversationParticipant.objects.filter(
            conversation=conversation, user=request.user
        ).exists()
        if not is_participant:
            return Response({'error': 'Not a participant of this conversation'}, status=status.HTTP_403_FORBIDDEN)

        queryset = Message.objects.filter(
            conversation=conversation, is_deleted=False
        ).select_related('sender').order_by('created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """Safe create with participant + payload validation to avoid 500s"""
        conversation_id = request.data.get('conversation')
        if not conversation_id:
            return Response({'error': 'conversation is required'}, status=status.HTTP_400_BAD_REQUEST)

        conversation_qs = Conversation.objects.filter(id=conversation_id)
        user_org = self._get_user_org()
        if not request.user.is_superuser:
            if not user_org:
                return Response({'error': 'Organization context required'}, status=status.HTTP_403_FORBIDDEN)
            conversation_qs = conversation_qs.filter(organization=user_org)

        conversation = conversation_qs.first()
        if not conversation:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure the requester is a participant of this conversation
        is_participant = ConversationParticipant.objects.filter(
            conversation=conversation, user=request.user
        ).exists()
        if not is_participant:
            return Response({'error': 'Not a participant of this conversation'}, status=status.HTTP_403_FORBIDDEN)

        payload = SendMessageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=payload.validated_data.get('content', ''),
            attachment=payload.validated_data.get('attachment'),
            reply_to_id=payload.validated_data.get('reply_to_id'),
            organization=conversation.organization,
            created_by=request.user,
        )

        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at'])

        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
    
    def get_queryset(self):
        user = self.request.user
        conversation_id = self.request.query_params.get('conversation')
        conversation_qs = Conversation.objects.filter(
            participants__user=user,
            participants__is_archived=False,
            is_deleted=False,
        )
        user_org = self._get_user_org()
        if not user.is_superuser:
            if not user_org:
                return Message.objects.none()
            conversation_qs = conversation_qs.filter(organization=user_org)

        if conversation_id:
            conversation_qs = conversation_qs.filter(id=conversation_id)

        return Message.objects.filter(
            conversation__in=conversation_qs.distinct(),
            is_deleted=False,
        ).select_related('sender').order_by('created_at')
    
    def perform_create(self, serializer):
        conversation_id = self.request.data.get('conversation')
        conversation_qs = Conversation.objects.filter(id=conversation_id)
        user_org = self._get_user_org()
        if not self.request.user.is_superuser:
            if not user_org:
                raise ValueError("Organization context required")
            conversation_qs = conversation_qs.filter(organization=user_org)
        conversation = conversation_qs.first()
        if not conversation:
            raise ValueError("Conversation not found")
        
        message = serializer.save(
            sender=self.request.user,
            conversation=conversation,
            organization=conversation.organization,
            created_by=self.request.user,
        )
        
        # Update conversation last_message_at
        conversation.last_message_at = timezone.now()
        conversation.save()
        
        # Broadcast via WebSocket to all connected clients
        self._broadcast_message(message, conversation)
        
        return message
    
    def _broadcast_message(self, message, conversation):
        """
        Broadcast new message to all WebSocket clients in the conversation room.
        Uses Channels layer to send to group.
        
        Falls back gracefully if Redis/Channels unavailable - message still saved to DB.
        """
        channel_layer = get_channel_layer()
        
        if channel_layer is None:
            # Channels not configured or Redis unavailable
            # Fail gracefully - message is still saved to DB
            logger = logging.getLogger(__name__)
            logger.debug('Channel layer not available - WebSocket broadcast skipped')
            return
        
        room_group_name = f"chat_{conversation.id}"
        
        try:
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': str(message.id),
                    'content': message.content,
                    'sender_id': str(message.sender.id),
                    'sender_name': message.sender.full_name,
                    'created_at': message.created_at.isoformat(),
                }
            )
        except Exception as e:
            # Log error but don't fail the request
            # Message is already saved to database
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to broadcast message via WebSocket: {e}")
    
    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        """Add a reaction to a message"""
        message = self.get_object()
        reaction_code = request.data.get('reaction')
        
        if not reaction_code:
            return Response({'error': 'Reaction code required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Toggle reaction
        existing = MessageReaction.objects.filter(message=message, user=request.user, reaction=reaction_code).first()
        if existing:
            existing.delete()
            return Response({'status': 'reaction removed'})
        else:
            MessageReaction.objects.create(message=message, user=request.user, reaction=reaction_code)
            return Response({'status': 'reaction added'})
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete - only sender can delete their own message"""
        message = self.get_object()
        if message.sender != request.user:
            return Response({'error': 'Cannot delete other users messages'}, status=status.HTTP_403_FORBIDDEN)
        
        message.is_deleted = True
        message.content = "[Message deleted]"
        message.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeetingRoomViewSet(OrganizationViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Expose active meeting rooms to authenticated users."""
    serializer_class = MeetingRoomSerializer
    permission_classes = [IsAuthenticated, ChatTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MeetingRoomFilter
    search_fields = ['name', 'room_id']
    ordering_fields = ['created_at', 'started_at']
    ordering = ['-created_at']
    lookup_field = 'room_id'

    def get_queryset(self):
        queryset = MeetingRoom.objects.filter(is_active=True)
        room_code = self.request.query_params.get('room_id')
        if room_code:
            queryset = queryset.filter(room_id=room_code)
        if self.request.user.is_superuser:
            return queryset
        org = self.request.user.get_organization()
        if not org:
            return MeetingRoom.objects.none()
        return queryset.filter(organization=org)


class MeetingScheduleViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """CRUD for meeting schedules with invite dispatch."""
    serializer_class = MeetingScheduleSerializer
    permission_classes = [IsAuthenticated, ChatTenantPermission, CanManageMeetings]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MeetingScheduleFilter
    search_fields = ['title']
    ordering_fields = ['start_time', 'created_at']
    ordering = ['-start_time']

    def get_queryset(self):
        base = MeetingSchedule.objects.select_related('meeting_room')
        room_param = self.request.query_params.get('meeting_room')
        if room_param:
            base = base.filter(meeting_room_id=room_param)
        if self.request.user.is_superuser:
            return base
        org = self.request.user.get_organization()
        if not org:
            return MeetingSchedule.objects.none()
        return base.filter(organization=org)

    def perform_create(self, serializer):
        schedule = serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        send_meeting_invites(schedule)
        return schedule


class MeetingRecordingViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Manage meeting recordings including uploads."""
    permission_classes = [IsAuthenticated, ChatTenantPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = MeetingRecordingFilter
    ordering_fields = ['started_at', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        base = MeetingRecording.objects.select_related('meeting_room')
        if self.request.user.is_superuser:
            return base
        org = self.request.user.get_organization()
        if not org:
            return MeetingRecording.objects.none()
        return base.filter(organization=org)

    def get_serializer_class(self):
        if self.action == 'create':
            return MeetingRecordingUploadSerializer
        return MeetingRecordingSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recording = serializer.save()
        read_serializer = MeetingRecordingSerializer(recording, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


def send_meeting_invites(schedule: MeetingSchedule):
    """Send email invitations for a schedule if recipients exist."""
    participants = schedule.participants.all()
    recipient_list = [user.email for user in participants if getattr(user, 'email', None)]
    if not recipient_list:
        return

    meeting_url = build_meeting_url(schedule.organization, schedule.meeting_room.room_id)
    subject = schedule.title or f"Meeting invitation for room {schedule.meeting_room.room_id}"
    start_dt = timezone.localtime(schedule.start_time)
    duration = schedule.end_time - schedule.start_time
    duration_minutes = max(int(duration.total_seconds() // 60), 1)

    body = (
        "You have been invited to a meeting.\n\n"
        f"Topic: {schedule.title or schedule.meeting_room.room_id}\n"
        f"Starts: {start_dt.strftime('%Y-%m-%d %H:%M %Z')}\n"
        f"Duration: {duration_minutes} minutes\n"
        f"Join Link: {meeting_url}\n"
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list,
            fail_silently=True,
        )
    except Exception:  # pragma: no cover - defensive logging
        logger.exception('Failed to send meeting invites for schedule %s', schedule.id)
