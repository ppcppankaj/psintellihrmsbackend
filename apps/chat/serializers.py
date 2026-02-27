"""
Chat Serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Count
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from django.utils import timezone
from apps.core.upload_validators import validate_upload as _validate_upload

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReaction,
    MeetingRoom,
    MeetingRecording,
    MeetingSchedule,
)
from .utils import build_meeting_url

User = get_user_model()


class OrganizationScopedCreateMixin:
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            organization = request.user.get_organization()
            if not organization:
                raise serializers.ValidationError("User is not assigned to an organization.")
            validated_data['organization'] = organization
        return super().create(validated_data)


class UserMiniSerializer(serializers.ModelSerializer):
    """Minimal user info for chat display"""
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'avatar']


class MessageSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    """Serializer for chat messages"""
    sender = UserMiniSerializer(read_only=True)
    reactions_summary = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'content', 'attachment',
            'is_system_message', 'reply_to', 'reactions_summary',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'sender', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        conversation = attrs.get('conversation')

        if conversation and request and request.user and request.user.is_authenticated:
            user_org = request.user.get_organization()
            if not request.user.is_superuser and user_org and conversation.organization_id != user_org.id:
                raise serializers.ValidationError("Cannot send message to a conversation in another organization.")

        return attrs
    
    @extend_schema_field({'type': 'object', 'additionalProperties': {'type': 'integer'}})
    def get_reactions_summary(self, obj):
        """Returns a dict of reaction counts, e.g., {'👍': 3, '❤️': 1}"""
        summary = obj.reactions.values('reaction').annotate(count=Count('id'))
        return {item['reaction']: item['count'] for item in summary}


class ConversationParticipantSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    """Serializer for conversation participants"""
    user = UserMiniSerializer(read_only=True)
    
    class Meta:
        model = ConversationParticipant
        fields = ['id', 'user', 'role', 'joined_at', 'last_read_at', 'is_muted', 'is_archived']


class ConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing conversations"""
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    participants_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'type', 'name', 'description', 'last_message_at',
            'last_message', 'unread_count', 'participants_preview'
        ]
    
    @extend_schema_field({'type': 'object', 'nullable': True, 'properties': {'content': {'type': 'string'}, 'sender_name': {'type': 'string'}, 'created_at': {'type': 'string', 'format': 'date-time'}}})
    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        if last:
            return {
                'content': last.content[:100],
                'sender_name': last.sender.full_name if last.sender else 'System',
                'created_at': last.created_at.isoformat()
            }
        return None
    
    @extend_schema_field(OpenApiTypes.INT)
    def get_unread_count(self, obj):
        user = self.context.get('request').user
        participant = obj.participants.filter(user=user).first()
        if participant:
            return obj.messages.filter(created_at__gt=participant.last_read_at).exclude(sender=user).count()
        return 0
    
    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_participants_preview(self, obj):
        # Return first 3 participants (excluding current user for direct chats)
        user = self.context.get('request').user
        participants = obj.participants.exclude(user=user).select_related('user')[:3]
        return UserMiniSerializer([p.user for p in participants], many=True).data


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for a single conversation"""
    participants = ConversationParticipantSerializer(many=True, read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'type', 'name', 'description', 'scope_id',
            'participants', 'last_message_at', 'created_at'
        ]


class CreateDirectConversationSerializer(serializers.Serializer):
    """Create a 1:1 direct message conversation"""
    user_id = serializers.UUIDField()
    initial_message = serializers.CharField(required=False, allow_blank=True)


class CreateGroupConversationSerializer(serializers.Serializer):
    """Create a group chat"""
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    user_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)


class SendMessageSerializer(serializers.Serializer):
    """Send a message to a conversation"""
    content = serializers.CharField(required=False, allow_blank=True)
    attachment = serializers.FileField(required=False, allow_null=True, validators=[_validate_upload])
    reply_to_id = serializers.UUIDField(required=False, allow_null=True)
    
    def validate(self, attrs):
        if not attrs.get('content') and not attrs.get('attachment'):
            raise serializers.ValidationError("Message must have content or an attachment.")
        return attrs


class MeetingScheduleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingSchedule
        fields = ['id', 'title', 'start_time', 'end_time']


class MeetingRoomSerializer(serializers.ModelSerializer):
    upcoming_schedule = serializers.SerializerMethodField()

    class Meta:
        model = MeetingRoom
        fields = [
            'id', 'room_id', 'is_active', 'started_at', 'ended_at',
            'created_at', 'updated_at', 'upcoming_schedule'
        ]
        read_only_fields = fields

    def get_upcoming_schedule(self, obj):
        schedule = obj.schedules.filter(start_time__gte=timezone.now()).order_by('start_time').first()
        if schedule:
            return MeetingScheduleSummarySerializer(schedule).data
        return None


class MeetingScheduleSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    meeting_url = serializers.SerializerMethodField()
    participants = UserMiniSerializer(many=True, read_only=True)
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )
    room_code = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = MeetingSchedule
        fields = [
            'id', 'meeting_room', 'room_code', 'title', 'start_time', 'end_time',
            'participants', 'participant_ids', 'meeting_url', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'meeting_room', 'participants', 'meeting_url', 'created_at', 'updated_at']

    def validate(self, attrs):
        room_code = attrs.pop('room_code', None)
        meeting_room = attrs.get('meeting_room')
        if not meeting_room and room_code:
            meeting_room = MeetingRoom.objects.filter(room_id=room_code).first()
            if not meeting_room:
                raise serializers.ValidationError({'room_code': 'Meeting room not found.'})
            attrs['meeting_room'] = meeting_room
        if not attrs.get('meeting_room'):
            raise serializers.ValidationError({'meeting_room': 'Meeting room is required.'})
        if attrs['end_time'] <= attrs['start_time']:
            raise serializers.ValidationError({'end_time': 'End time must be after start time.'})
        return attrs

    def create(self, validated_data):
        participant_ids = validated_data.pop('participant_ids', [])
        meeting_room = validated_data['meeting_room']
        request = self.context.get('request')
        if request and not request.user.is_superuser:
            org = request.user.get_organization()
            if not org or meeting_room.organization_id != org.id:
                raise serializers.ValidationError('Cannot schedule meeting for another organization.')
        schedule = super().create(validated_data)
        self._assign_participants(schedule, participant_ids)
        return schedule

    def _assign_participants(self, schedule, participant_ids):
        if not participant_ids:
            return
        from django.contrib.auth import get_user_model

        User = get_user_model()
        allowed_org = schedule.organization
        users = User.objects.filter(id__in=participant_ids)
        valid_users = [user for user in users if user.get_organization() and user.get_organization().id == allowed_org.id]
        if valid_users:
            schedule.participants.add(*valid_users)

    def get_meeting_url(self, obj):
        return build_meeting_url(obj.organization, obj.meeting_room.room_id)


class MeetingRecordingSerializer(serializers.ModelSerializer):
    recorded_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = MeetingRecording
        fields = [
            'id', 'meeting_room', 'recording_file', 'recorded_by',
            'started_at', 'ended_at', 'created_at'
        ]
        read_only_fields = ['id', 'meeting_room', 'recording_file', 'recorded_by', 'created_at']


class MeetingRecordingUploadSerializer(serializers.Serializer):
    room_id = serializers.CharField(required=False)
    meeting_room = serializers.UUIDField(required=False)
    recording_file = serializers.FileField(validators=[_validate_upload])
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        room_id = attrs.get('room_id')
        meeting_room_id = attrs.get('meeting_room')
        meeting_room = None

        if meeting_room_id:
            meeting_room = MeetingRoom.objects.filter(id=meeting_room_id).first()
            if not meeting_room:
                raise serializers.ValidationError({'meeting_room': 'Meeting room not found.'})
        elif room_id:
            meeting_room = MeetingRoom.objects.filter(room_id=room_id).first()
            if not meeting_room:
                raise serializers.ValidationError({'room_id': 'Meeting room not found.'})
        else:
            raise serializers.ValidationError({'meeting_room': 'Provide meeting_room id or room_id.'})
        request = self.context.get('request')
        if request and not request.user.is_superuser:
            org = request.user.get_organization()
            if not org or org.id != meeting_room.organization_id:
                raise serializers.ValidationError('Cannot upload recording for another organization.')
        attrs['meeting_room'] = meeting_room
        return attrs

    def create(self, validated_data):
        meeting_room = validated_data.pop('meeting_room')
        request = self.context.get('request')
        return MeetingRecording.objects.create(
            meeting_room=meeting_room,
            organization=meeting_room.organization,
            recorded_by=getattr(request, 'user', None),
            recording_file=validated_data['recording_file'],
            started_at=validated_data.get('started_at'),
            ended_at=validated_data.get('ended_at'),
        )
