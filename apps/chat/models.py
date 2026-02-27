from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.models import OrganizationEntity


class MeetingRoom(OrganizationEntity):
    """Tenant-scoped WebRTC room for video meetings."""

    room_id = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='meeting_rooms',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'room_id']),
            models.Index(fields=['organization', 'is_active']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Room {self.room_id} ({self.organization})"

    def clean(self):
        if not self.room_id:
            raise ValidationError('Room ID is required for meeting rooms.')

    def save(self, *args, **kwargs):
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)


class MeetingRecording(OrganizationEntity):
    """Stored meeting recordings uploaded from clients."""

    meeting_room = models.ForeignKey(
        MeetingRoom,
        on_delete=models.CASCADE,
        related_name='recordings',
    )
    recording_file = models.FileField(upload_to='meeting_recordings/')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='meeting_recordings',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'meeting_room']),
            models.Index(fields=['organization', 'created_at']),
        ]

    def __str__(self):
        return f"Recording {self.recording_file.name}"

    def clean(self):
        if self.meeting_room and self.organization_id and self.meeting_room.organization_id != self.organization_id:
            raise ValidationError('Recording must belong to the same organization as the meeting room.')

    def save(self, *args, **kwargs):
        if not self.organization_id and self.meeting_room_id:
            self.organization = self.meeting_room.organization
        self.clean()
        super().save(*args, **kwargs)


class MeetingSchedule(OrganizationEntity):
    """Calendar entry for upcoming meetings with invitations."""

    meeting_room = models.ForeignKey(
        MeetingRoom,
        on_delete=models.CASCADE,
        related_name='schedules',
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    title = models.CharField(max_length=255, blank=True)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='meeting_schedules',
        blank=True,
    )

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['organization', 'start_time']),
            models.Index(fields=['meeting_room', 'start_time']),
        ]

    def __str__(self):
        return self.title or f"Meeting {self.meeting_room.room_id}"

    def clean(self):
        if self.meeting_room and self.organization_id and self.meeting_room.organization_id != self.organization_id:
            raise ValidationError('Meeting room organization mismatch.')
        if self.end_time and self.start_time and self.end_time <= self.start_time:
            raise ValidationError('End time must be after start time.')

    def save(self, *args, **kwargs):
        if not self.organization_id and self.meeting_room_id:
            self.organization = self.meeting_room.organization
        self.clean()
        super().save(*args, **kwargs)

class Conversation(OrganizationEntity):
    """
    Represents a chat conversation.
    Can be a direct message (1:1), a group chat, a department chat, etc.
    """

    class Type(models.TextChoices):
        DIRECT = 'direct', _('Direct Message')
        GROUP = 'group', _('Group Chat')
        DEPARTMENT = 'department', _('Department Chat')
        ANNOUNCEMENT = 'announcement', _('Announcement Channel')
        # PROJECT = 'project', _('Project Chat') # Future scope

    type = models.CharField(max_length=20, choices=Type.choices, default=Type.DIRECT)
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Required for Group/Department chats")
    description = models.TextField(blank=True, null=True)
    
    # Optional linking to other entities
    # For Department chats, scope_id could be the Department ID
    scope_id = models.CharField(max_length=255, blank=True, null=True) 
    
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return self.name or f"{self.get_type_display()} ({self.id})"

    def save(self, *args, **kwargs):
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        super().save(*args, **kwargs)

class ConversationParticipant(OrganizationEntity):
    """
    Links users to conversations with specific roles and state.
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', _('Admin')
        MEMBER = 'member', _('Member')
        
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
    
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    
    # State
    last_read_at = models.DateTimeField(auto_now_add=True)
    is_muted = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('conversation', 'user')
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
        
    def __str__(self):
        return f"{self.user} in {self.conversation}"

    def clean(self):
        if self.conversation_id:
            conversation_org_id = self.conversation.organization_id
            if self.organization_id and self.organization_id != conversation_org_id:
                raise ValidationError("Participant organization must match conversation organization.")

            user_org = self.user.get_organization() if self.user_id else None
            if user_org and user_org.id != conversation_org_id:
                raise ValidationError("Cannot add user from a different organization to this conversation.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.conversation_id:
            self.organization = self.conversation.organization
        if not self.organization_id and self.user_id:
            self.organization = self.user.get_organization()
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)

class Message(OrganizationEntity):
    """
    A single message in a conversation.
    """

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sent_messages')
    
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to='chat_attachments/', blank=True, null=True)
    
    is_system_message = models.BooleanField(default=False, help_text="If true, sender is ignored/system")
    
    # Reply support
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
        
    def __str__(self):
        return f"Message {self.id} from {self.sender}"

    def clean(self):
        if self.conversation_id:
            conversation_org_id = self.conversation.organization_id
            if self.organization_id and self.organization_id != conversation_org_id:
                raise ValidationError("Message organization must match conversation organization.")

            if self.sender_id:
                sender_org = self.sender.get_organization()
                if not sender_org or sender_org.id != conversation_org_id:
                    raise ValidationError("Message sender must belong to the same organization as the conversation.")

        if self.reply_to_id and self.conversation_id:
            if self.reply_to.conversation_id != self.conversation_id:
                raise ValidationError("Reply target must belong to the same conversation.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.conversation_id:
            self.organization = self.conversation.organization
        if not self.organization_id and self.sender_id:
            self.organization = self.sender.get_organization()
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)

class MessageReaction(OrganizationEntity):
    """
    Reactions to messages (e.g., thumbs up, heart).
    """

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reaction = models.CharField(max_length=50) # store emoji char or code
    
    class Meta:
        unique_together = ('message', 'user', 'reaction')
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]

    def clean(self):
        if self.message_id:
            message_org_id = self.message.organization_id
            if self.organization_id and self.organization_id != message_org_id:
                raise ValidationError("Reaction organization must match message organization.")

            if self.user_id:
                user_org = self.user.get_organization()
                if not user_org or user_org.id != message_org_id:
                    raise ValidationError("Reaction user must belong to the same organization as the message.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.message_id:
            self.organization = self.message.organization
        if not self.organization_id and self.user_id:
            self.organization = self.user.get_organization()
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)
