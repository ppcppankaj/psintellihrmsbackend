"""Notification orchestration services"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification, NotificationPreference, NotificationTemplate
from .notification_router import NotificationRouter
from .template_renderer import RenderedNotification, TemplateRenderer


class NotificationService:
    """High-level orchestration for notification workflows."""

    renderer = TemplateRenderer()
    router = NotificationRouter()

    # --------------------------------------------------------------------- API
    @classmethod
    def notify(
        cls,
        *,
        organization_id: str | None = None,
        user=None,
        employee=None,
        recipient=None,
        template_code: str | None = None,
        template: NotificationTemplate | None = None,
        context: Dict[str, Any] | None = None,
        subject: str | None = None,
        body: str | None = None,
        title: str | None = None,
        message: str | None = None,
        channel: str = 'in_app',
        entity_type: str | None = None,
        entity_id=None,
        priority: str = 'normal',
        metadata: Dict[str, Any] | None = None,
        scheduled_for: datetime | None = None,
        notification_type: str | None = None,
        send_async: bool = True,
        respect_preferences: bool = True,
    ) -> Notification | None:
        employee_instance = cls._resolve_employee(user=user, employee=employee, recipient=recipient)
        if not employee_instance:
            return None

        organization_id = organization_id or getattr(employee_instance, 'organization_id', None)
        if not organization_id:
            return None

        template_obj = template or cls._get_template(template_code, organization_id)
        render_result = cls._render_template(template_obj, context=context or {}) if template_obj else None

        resolved_subject = subject or title or (render_result.subject if render_result else 'Notification')
        resolved_body = body or message or (render_result.body if render_result else '')
        resolved_channel = template_obj.channel if template_obj else channel
        immutable_metadata = metadata or {}
        merged_metadata = {
            **immutable_metadata,
            'notification_type': notification_type,
            'context': context or {},
        }
        if render_result:
            merged_metadata['missing_variables'] = render_result.missing_variables
            merged_metadata['template_code'] = template_obj.code

        preference = cls._get_preferences(employee_instance) if respect_preferences else None
        resolved_channel = cls._apply_channel_preferences(resolved_channel, preference)
        scheduled_for = cls._apply_quiet_hours(preference, scheduled_for)
        eta = scheduled_for if scheduled_for and scheduled_for > timezone.now() else None

        notification = Notification.objects.create(
            organization_id=organization_id,
            recipient=employee_instance,
            template=template_obj,
            channel=resolved_channel,
            subject=resolved_subject,
            body=resolved_body,
            status='scheduled' if eta else 'pending',
            priority=priority,
            metadata=merged_metadata,
            scheduled_for=scheduled_for,
            entity_type=entity_type or '',
            entity_id=entity_id,
        )

        cls._queue_delivery(notification, eta=eta)

        return notification

    @classmethod
    def bulk_notify(
        cls,
        *,
        organization_id: str,
        recipient_ids: Sequence[str],
        **payload,
    ) -> Dict[str, Any]:
        from apps.employees.models import Employee

        employees = list(
            Employee.objects.filter(
                id__in=recipient_ids,
                organization_id=organization_id,
                is_active=True,
            )
        )
        found_ids = {str(employee.id) for employee in employees}
        missing_ids = [str(rid) for rid in recipient_ids if str(rid) not in found_ids]

        created: List[str] = []
        for employee in employees:
            result = cls.notify(organization_id=organization_id, employee=employee, **payload)
            if result:
                created.append(str(result.id))

        return {'created': created, 'missing_recipients': missing_ids}

    @classmethod
    def mark_as_read(cls, notification_id: str, user) -> bool:
        notification = cls._safe_queryset(Notification.objects.all(), user=user).filter(id=notification_id).first()
        if not notification:
            return False
        notification.mark_read()
        return True

    @classmethod
    def mark_all_as_read(cls, user) -> int:
        queryset = cls._safe_queryset(Notification.objects.all(), user=user).exclude(status='read')
        updated = queryset.update(status='read', read_at=timezone.now())
        return updated

    @classmethod
    def unread_count(cls, user) -> int:
        return cls._safe_queryset(Notification.objects.all(), user=user).exclude(status='read').count()

    @classmethod
    def send_digest(cls, *, organization_id: str, digest_type: str = 'daily', user_ids: Sequence[str] | None = None) -> Dict[str, Any]:
        from apps.employees.models import Employee

        window = timedelta(days=1 if digest_type == 'daily' else 7)
        cutoff = timezone.now() - window

        employees = Employee.objects.filter(
            organization_id=organization_id,
            is_active=True,
        )
        if user_ids:
            employees = employees.filter(user_id__in=user_ids)

        dispatched = 0
        for employee in employees:
            unread = Notification.objects.filter(recipient=employee, created_at__gte=cutoff).exclude(status='read')
            if not unread.exists():
                continue
            subjects = list(unread.values_list('subject', flat=True)[:5])
            digest_body = cls._build_digest_body(subjects, unread.count())
            result = cls.notify(
                organization_id=organization_id,
                employee=employee,
                subject=f"{digest_type.title()} Digest",  # type: ignore[arg-type]
                body=digest_body,
                channel='email',
                respect_preferences=False,
            )
            if result:
                dispatched += 1
        return {'dispatched': dispatched, 'digest_type': digest_type}

    @classmethod
    def send_push_notifications(
        cls,
        *,
        organization_id: str,
        recipient_ids: Sequence[str],
        title: str,
        body: str,
        data: Dict[str, Any] | None = None,
        priority: str = 'normal',
    ) -> Dict[str, Any]:
        payload = {
            'subject': title,
            'body': body,
            'channel': 'push',
            'priority': priority,
            'metadata': {'data': data or {}},
        }
        return cls.bulk_notify(organization_id=organization_id, recipient_ids=recipient_ids, **payload)

    # --------------------------------------------------------------- Internals
    @staticmethod
    def _resolve_employee(user=None, employee=None, recipient=None):
        if employee:
            return employee
        if recipient:
            return recipient
        if user is None:
            return None
        return getattr(user, 'employee', None)

    @staticmethod
    def _get_template(template_code: str | None, organization_id: str | None) -> NotificationTemplate | None:
        if not template_code or not organization_id:
            return None
        return NotificationTemplate.objects.filter(
            organization_id=organization_id,
            code=template_code,
            is_active=True,
        ).first()

    @classmethod
    def _render_template(cls, template: NotificationTemplate, context: Dict[str, Any]) -> RenderedNotification:
        return cls.renderer.render(template, context=context)

    @staticmethod
    def _get_preferences(employee) -> NotificationPreference | None:
        return getattr(employee.user, 'notification_prefs', None)

    @staticmethod
    def _apply_channel_preferences(channel: str, preference: NotificationPreference | None) -> str:
        if not preference:
            return channel
        channel_map = {
            'email': preference.email_enabled,
            'push': preference.push_enabled,
            'sms': preference.sms_enabled,
        }
        if channel in channel_map and not channel_map[channel]:
            return 'in_app'
        return channel

    @staticmethod
    def _apply_quiet_hours(preference: NotificationPreference | None, scheduled_for: datetime | None) -> datetime | None:
        if not preference or not preference.quiet_hours_enabled:
            return scheduled_for
        now = timezone.now()
        start = preference.quiet_hours_start
        end = preference.quiet_hours_end
        if not start or not end:
            return scheduled_for
        in_quiet = NotificationService._within_quiet_hours(now.time(), start, end)
        if not in_quiet:
            return scheduled_for
        next_time = datetime.combine(now.date(), end)
        if end <= start:
            next_time += timedelta(days=1)
        return timezone.make_aware(next_time) if timezone.is_naive(next_time) else next_time

    @staticmethod
    def _within_quiet_hours(current_time, start, end) -> bool:
        if start <= end:
            return start <= current_time <= end
        return current_time >= start or current_time <= end

    @staticmethod
    def _build_digest_body(subjects: List[str], count: int) -> str:
        preview = '\n'.join(f"- {subject}" for subject in subjects)
        if count > len(subjects):
            preview += f"\n...and {count - len(subjects)} more"
        return f"You have {count} unread notification(s):\n{preview}"

    @classmethod
    def _queue_delivery(cls, notification: Notification, eta: datetime | None = None) -> None:
        from apps.notifications.tasks.send_notification_task import send_notification_task

        kwargs = {
            'organization_id': str(notification.organization_id),
            'notification_id': str(notification.id),
        }
        if eta:
            send_notification_task.apply_async(kwargs=kwargs, eta=eta)
        else:
            send_notification_task.delay(**kwargs)

    @classmethod
    def dispatch_immediately(cls, notification: Notification) -> None:
        cls.router.dispatch(notification)

    @classmethod
    def _safe_queryset(cls, queryset, user):
        if not user or not user.is_authenticated:
            return queryset.none()
        organization_id = getattr(user, 'organization_id', None)
        return queryset.filter(organization_id=organization_id, recipient__user=user)
