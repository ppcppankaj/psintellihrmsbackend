"""Channel routing for notifications"""
from __future__ import annotations

from typing import Any, Callable, Dict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.notifications.models import Notification


class NotificationRouter:
    """Route notifications to appropriate delivery channels."""

    def __init__(self) -> None:
        self.channel_handlers: Dict[str, Callable[[Notification], None]] = {
            'in_app': self._send_in_app,
            'email': self._send_email,
            'push': self._send_push,
            'sms': self._send_sms,
            'whatsapp': self._send_whatsapp,
            'teams': self._send_collaboration,
            'slack': self._send_collaboration,
        }

    def dispatch(self, notification: Notification) -> None:
        handler = self.channel_handlers.get(notification.channel, self._send_in_app)
        notification.delivery_attempts += 1
        notification.save(update_fields=['delivery_attempts'])
        try:
            handler(notification)
            notification.mark_sent()
            self._push_realtime(notification)
        except Exception as exc:  # pragma: no cover - logging hook
            metadata = {**notification.metadata}
            metadata['last_error'] = str(exc)
            notification.metadata = metadata
            notification.mark_failed(str(exc))

    # Channel implementations -------------------------------------------------
    def _send_in_app(self, notification: Notification) -> None:
        # In-app notifications live within the database; realtime push covers UX.
        return None

    def _send_email(self, notification: Notification) -> None:
        if not getattr(settings, 'DEFAULT_FROM_EMAIL', None):
            return
        recipient_email = getattr(notification.recipient.user, 'email', None)
        if not recipient_email:
            raise ValueError('Recipient has no email address')
        send_mail(
            subject=notification.subject,
            message=notification.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )

    def _send_push(self, notification: Notification) -> None:
        # Hook into push providers (FCM/OneSignal/etc.).
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"push_{notification.recipient_id}",
            {
                'type': 'broadcast.notification',
                'event': 'notification.push',
                'payload': self._serialize(notification),
            },
        )

    def _send_sms(self, notification: Notification) -> None:
        # Integrate with SMS gateway (Twilio, AWS SNS, etc.). Placeholder only.
        return None

    def _send_whatsapp(self, notification: Notification) -> None:
        # Implement via WhatsApp Business API when available.
        return None

    def _send_collaboration(self, notification: Notification) -> None:
        # Placeholder for Teams/Slack connectors.
        return None

    # Helpers -----------------------------------------------------------------
    def _push_realtime(self, notification: Notification) -> None:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        user_id = getattr(notification.recipient, 'user_id', None)
        if not user_id:
            return
        group_name = f"notifications_{user_id}"
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'broadcast.notification',
                'event': 'notification.update',
                'payload': self._serialize(notification),
            },
        )

    def _serialize(self, notification: Notification) -> Dict[str, Any]:
        return {
            'id': str(notification.id),
            'subject': notification.subject,
            'body': notification.body,
            'status': notification.status,
            'channel': notification.channel,
            'priority': notification.priority,
            'sent_at': notification.sent_at.isoformat() if notification.sent_at else None,
            'read_at': notification.read_at.isoformat() if notification.read_at else None,
            'metadata': notification.metadata,
            'entity_type': notification.entity_type,
            'entity_id': str(notification.entity_id) if notification.entity_id else None,
            'organization_id': str(notification.organization_id),
            'recipient_id': str(notification.recipient_id),
            'timestamp': timezone.now().isoformat(),
        }
