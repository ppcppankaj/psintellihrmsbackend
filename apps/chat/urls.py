"""
Chat URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConversationViewSet,
    MessageViewSet,
    MeetingRoomViewSet,
    MeetingScheduleViewSet,
    MeetingRecordingViewSet,
)

router = DefaultRouter()
router.register('conversations', ConversationViewSet, basename='conversation')
router.register('messages', MessageViewSet, basename='message')
router.register('meeting-rooms', MeetingRoomViewSet, basename='meeting-room')
router.register('meeting-schedules', MeetingScheduleViewSet, basename='meeting-schedule')
router.register('meeting-recordings', MeetingRecordingViewSet, basename='meeting-recording')

urlpatterns = [
    path('', include(router.urls)),
]
