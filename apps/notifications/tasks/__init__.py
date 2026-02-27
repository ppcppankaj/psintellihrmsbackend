"""Notification Celery tasks"""
from .send_notification_task import send_notification_task

__all__ = ['send_notification_task']
