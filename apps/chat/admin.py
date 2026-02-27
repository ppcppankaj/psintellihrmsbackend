from django.contrib import admin
from django.contrib.auth import get_user_model
from apps.core.models import Organization
from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReaction,
    MeetingRoom,
    MeetingRecording,
    MeetingSchedule,
)

User = get_user_model()


class ChatOrgAdminMixin:
    def _get_user_org(self, request):
        if request.user.is_superuser:
            return None
        return request.user.get_organization()

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        user_org = self._get_user_org(request)
        if user_org:
            return qs.filter(organization=user_org)

        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        user_org = self._get_user_org(request)
        if not user_org:
            kwargs["queryset"] = db_field.related_model.objects.none()
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == "organization":
            kwargs["queryset"] = Organization.objects.filter(id=user_org.id)
        elif db_field.related_model is User:
            kwargs["queryset"] = User.objects.filter(
                organization_memberships__organization=user_org,
                organization_memberships__is_active=True,
            ).distinct()
        elif db_field.related_model is Conversation:
            kwargs["queryset"] = Conversation.objects.filter(organization=user_org, is_deleted=False)
        elif db_field.related_model is Message:
            kwargs["queryset"] = Message.objects.filter(organization=user_org, is_deleted=False)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "organization") and not request.user.is_superuser:
            user_org = self._get_user_org(request)
            if user_org:
                obj.organization = user_org

        if hasattr(obj, "created_by") and not obj.created_by:
            obj.created_by = request.user
        if hasattr(obj, "updated_by"):
            obj.updated_by = request.user

        super().save_model(request, obj, form, change)


class ConversationParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 0
    autocomplete_fields = ['user']
    readonly_fields = ['joined_at', 'last_read_at']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.related_model is User:
            user_org = request.user.get_organization()
            if user_org:
                kwargs["queryset"] = User.objects.filter(
                    organization_memberships__organization=user_org,
                    organization_memberships__is_active=True,
                ).distinct()
            else:
                kwargs["queryset"] = User.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['created_at']
    autocomplete_fields = ['sender']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and db_field.related_model is User:
            user_org = request.user.get_organization()
            if user_org:
                kwargs["queryset"] = User.objects.filter(
                    organization_memberships__organization=user_org,
                    organization_memberships__is_active=True,
                ).distinct()
            else:
                kwargs["queryset"] = User.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Conversation)
class ConversationAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'organization',
        'type',
        'name',
        'scope_id',
        'last_message_at',
        'created_at',
    )
    list_filter = ('organization', 'type', 'created_at')
    search_fields = ('name', 'description', 'scope_id')
    readonly_fields = ('last_message_at', 'created_at', 'updated_at')
    inlines = [ConversationParticipantInline]
    ordering = ('-last_message_at',)


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'organization',
        'conversation',
        'user',
        'role',
        'is_muted',
        'is_archived',
        'joined_at',
    )
    list_filter = ('organization', 'role', 'is_muted', 'is_archived')
    search_fields = ('conversation__name', 'user__username', 'user__email')
    autocomplete_fields = ['conversation', 'user']
    readonly_fields = ('joined_at', 'last_read_at')


@admin.register(Message)
class MessageAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'organization',
        'conversation',
        'sender',
        'short_content',
        'is_system_message',
        'created_at',
    )
    list_filter = ('organization', 'is_system_message', 'created_at')
    search_fields = ('content', 'sender__username', 'conversation__name')
    autocomplete_fields = ['conversation', 'sender', 'reply_to']
    readonly_fields = ('created_at', 'updated_at')
    inlines = []  # You can add reactions inline if you want

    def short_content(self, obj):
        return obj.content[:50] + "..." if obj.content and len(obj.content) > 50 else obj.content

    short_content.short_description = "Content"


@admin.register(MessageReaction)
class MessageReactionAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'organization', 'message', 'user', 'reaction', 'created_at')
    list_filter = ('organization', 'reaction', 'created_at')
    search_fields = ('message__content', 'user__username', 'reaction')
    autocomplete_fields = ['message', 'user']


@admin.register(MeetingRoom)
class MeetingRoomAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = (
        'room_id',
        'organization',
        'created_by',
        'is_active',
        'started_at',
        'ended_at',
        'created_at',
    )
    list_filter = ('organization', 'is_active', 'started_at')
    search_fields = ('room_id', 'created_by__email', 'organization__name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['created_by']


@admin.register(MeetingRecording)
class MeetingRecordingAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = (
        'recording_file',
        'meeting_room',
        'organization',
        'recorded_by',
        'started_at',
        'ended_at',
        'created_at',
    )
    list_filter = ('organization', 'meeting_room', 'created_at')
    search_fields = ('recording_file', 'meeting_room__room_id')
    autocomplete_fields = ['meeting_room', 'recorded_by']
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MeetingSchedule)
class MeetingScheduleAdmin(ChatOrgAdminMixin, admin.ModelAdmin):
    list_display = (
        'title',
        'meeting_room',
        'organization',
        'start_time',
        'end_time',
        'created_by',
    )
    list_filter = ('organization', 'start_time')
    search_fields = ('title', 'meeting_room__room_id')
    autocomplete_fields = ['meeting_room', 'participants']
    filter_horizontal = ['participants']
    readonly_fields = ('created_at', 'updated_at')
