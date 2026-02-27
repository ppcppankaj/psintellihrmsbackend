"""Billing tasks package – re-exports for Celery auto-discovery."""
from .subscription_expiry_task import subscription_expiry_task
from .email_tasks import (
    send_expiry_3_day_email,
    send_expiry_1_day_email,
    send_expired_email,
    send_grace_email,
    send_suspended_email,
)

# Backward compatibility alias
check_subscription_expiry = subscription_expiry_task
process_subscription_expiry_reminders = subscription_expiry_task

__all__ = [
    'subscription_expiry_task',
    'check_subscription_expiry',
    'process_subscription_expiry_reminders',
    'send_expiry_3_day_email',
    'send_expiry_1_day_email',
    'send_expired_email',
    'send_grace_email',
    'send_suspended_email',
]
