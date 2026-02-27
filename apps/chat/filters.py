"""Chat app filters."""
import django_filters
from .models import (
    MeetingRoom, MeetingRecording, MeetingSchedule,
    Conversation, ConversationParticipant, Message, MessageReaction,
)


class MeetingRoomFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    started_after = django_filters.DateTimeFilter(field_name='started_at', lookup_expr='gte')

    class Meta:
        model = MeetingRoom
        fields = ['is_active']


class MeetingRecordingFilter(django_filters.FilterSet):
    meeting_room = django_filters.UUIDFilter()
    recorded_by = django_filters.UUIDFilter()

    class Meta:
        model = MeetingRecording
        fields = ['meeting_room', 'recorded_by']


class MeetingScheduleFilter(django_filters.FilterSet):
    meeting_room = django_filters.UUIDFilter()
    start_after = django_filters.DateTimeFilter(field_name='start_time', lookup_expr='gte')
    start_before = django_filters.DateTimeFilter(field_name='start_time', lookup_expr='lte')

    class Meta:
        model = MeetingSchedule
        fields = ['meeting_room']


class ConversationFilter(django_filters.FilterSet):
    type = django_filters.ChoiceFilter(choices=[
        ('direct', 'Direct'), ('group', 'Group'),
        ('department', 'Department'), ('announcement', 'Announcement'),
    ])
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Conversation
        fields = ['type', 'is_active']


class MessageFilter(django_filters.FilterSet):
    conversation = django_filters.UUIDFilter()
    sender = django_filters.UUIDFilter()
    is_system_message = django_filters.BooleanFilter()
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Message
        fields = ['conversation', 'sender', 'is_system_message']
