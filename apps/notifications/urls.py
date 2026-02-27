"""Notifications URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationViewSet, NotificationTemplateViewSet, NotificationPreferenceViewSet
)

router = DefaultRouter()
router.register(r'templates', NotificationTemplateViewSet, basename='notification-template')
router.register(r'preferences', NotificationPreferenceViewSet, basename='notification-preference')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [path('', include(router.urls))]

