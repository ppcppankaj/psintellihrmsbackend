"""Subscription expiry reminders and grace-period logic"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.billing.models import OrganizationSubscription

logger = logging.getLogger(__name__)


class RenewalService:
    """Handles subscription expiry reminders and grace logic."""

    REMINDER_3_DAYS = 3
    REMINDER_1_DAY = 1

    @classmethod
    def build_renewal_url(cls, organization):
        base_url = (getattr(settings, 'BILLING_PORTAL_BASE_URL', '') or '').rstrip('/')
        if not organization:
            return ''
        if base_url:
            return f"{base_url}/billing/renew/{organization.id}"
        return f"/billing/renew/{organization.id}"

    @classmethod
    def process_subscription(cls, subscription):
        """Run the daily lifecycle check for a single subscription."""
        events = {
            'reminder_3': False,
            'reminder_1': False,
            'expired': False,
            'grace': False,
            'suspended': False,
        }

        if not subscription or not subscription.expiry_date or not subscription.is_active:
            return events

        today = timezone.now().date()
        days_until_expiry = (subscription.expiry_date - today).days

        if days_until_expiry == cls.REMINDER_3_DAYS and not subscription.reminder_sent_3_days_at:
            events['reminder_3'] = True
            cls._enqueue_email_task('reminder_3', subscription.id)
        if days_until_expiry == cls.REMINDER_1_DAY and not subscription.reminder_sent_1_day_at:
            events['reminder_1'] = True
            cls._enqueue_email_task('reminder_1', subscription.id)
        if subscription.expiry_date == today and not subscription.expired_notice_sent_at:
            events['expired'] = True
            cls._enqueue_email_task('expired', subscription.id)

        if subscription.expiry_date < today:
            if cls.is_within_grace(subscription):
                cls.mark_org_past_due(subscription)
                if not subscription.grace_notice_sent_at:
                    events['grace'] = True
                    cls._enqueue_email_task('grace', subscription.id)
            elif cls.has_grace_passed(subscription):
                if not subscription.suspension_notice_sent_at:
                    events['suspended'] = True
                    cls._enqueue_email_task('suspended', subscription.id)
                subscription.deactivate(reason='grace_period_ended')
        else:
            cls.mark_org_active(subscription)

        return events

    @classmethod
    def is_within_grace(cls, subscription):
        return subscription.is_in_grace_period

    @classmethod
    def has_grace_passed(cls, subscription):
        return subscription.grace_period_lapsed

    @classmethod
    def mark_org_past_due(cls, subscription):
        if not subscription.organization_id:
            return
        org = subscription.organization
        if org.subscription_status != 'past_due':
            org.subscription_status = 'past_due'
            org.save(update_fields=['subscription_status', 'updated_at'])

    @classmethod
    def mark_org_active(cls, subscription):
        if not subscription.organization_id:
            return
        org = subscription.organization
        desired = 'trial' if subscription.is_trial else 'active'
        if org.subscription_status != desired:
            org.subscription_status = desired
            org.save(update_fields=['subscription_status', 'updated_at'])

    @staticmethod
    def _enqueue_email_task(event_key, subscription_id):
        if not subscription_id:
            return
        try:
            from apps.billing.billing_tasks import (
                send_expiry_3_day_email,
                send_expiry_1_day_email,
                send_expired_email,
                send_grace_email,
                send_suspended_email,
            )
        except Exception:
            logger.exception('Unable to import billing tasks for event %s', event_key)
            return

        task_map = {
            'reminder_3': send_expiry_3_day_email,
            'reminder_1': send_expiry_1_day_email,
            'expired': send_expired_email,
            'grace': send_grace_email,
            'suspended': send_suspended_email,
        }
        task = task_map.get(event_key)
        if task:
            task.delay(subscription_id)


class RenewalEmailService:
    """Renders and sends subscription reminder emails."""

    TEMPLATE_MAP = {
        'reminder_3': 'emails/subscription_expiry_3_days.html',
        'reminder_1': 'emails/subscription_expiry_1_day.html',
        'expired': 'emails/subscription_expired.html',
        'grace': 'emails/grace_period_started.html',
        'suspended': 'emails/subscription_suspended.html',
    }
    SUBJECT_MAP = {
        'reminder_3': '{plan} subscription expires in 3 days',
        'reminder_1': '{plan} subscription expires tomorrow',
        'expired': '{plan} subscription expired today',
        'grace': '{plan} subscription entered grace period',
        'suspended': '{plan} subscription has been suspended',
    }
    FIELD_MAP = {
        'reminder_3': 'reminder_sent_3_days_at',
        'reminder_1': 'reminder_sent_1_day_at',
        'expired': 'expired_notice_sent_at',
        'grace': 'grace_notice_sent_at',
        'suspended': 'suspension_notice_sent_at',
    }
    FIELD_ALIASES = {
        'reminder_3': ['last_3_day_email_sent'],
        'reminder_1': ['last_1_day_email_sent'],
        'expired': ['expired_email_sent'],
        'grace': ['grace_email_sent'],
        'suspended': ['suspended_email_sent'],
    }

    @classmethod
    def send_event_email(cls, subscription_id, event_key, *, subscription=None):
        if event_key not in cls.TEMPLATE_MAP:
            logger.warning('Unknown renewal email event: %s', event_key)
            return False

        qs = (
            OrganizationSubscription.all_objects
            if hasattr(OrganizationSubscription, 'all_objects')
            else OrganizationSubscription.objects
        )
        subscription = (
            subscription
            or qs.select_related('organization', 'plan').filter(id=subscription_id).first()
        )
        if not subscription or not subscription.organization_id:
            logger.warning('Subscription %s not found for %s email', subscription_id, event_key)
            return False

        organization = subscription.organization
        recipient = getattr(organization, 'email', None)
        if not recipient:
            return False

        subject = cls.SUBJECT_MAP.get(event_key, 'Subscription update').format(
            plan=subscription.plan.name if subscription.plan_id else 'HRMS',
        )
        context = cls._build_context(subscription)
        html_body = render_to_string(cls.TEMPLATE_MAP[event_key], context)
        text_body = strip_tags(html_body)

        smtp_settings = cls._get_smtp_settings(organization)
        from_email = smtp_settings.get('from_email') or settings.DEFAULT_FROM_EMAIL
        connection = cls._resolve_connection(smtp_settings)

        email = EmailMultiAlternatives(
            subject=subject, body=text_body,
            from_email=from_email, to=[recipient],
            connection=connection,
        )
        email.attach_alternative(html_body, 'text/html')
        email.send()
        cls._mark_notice(subscription, event_key)
        return True

    @classmethod
    def was_notice_sent(cls, subscription, event_key):
        field_name = cls.FIELD_MAP.get(event_key)
        if field_name and getattr(subscription, field_name, None):
            return True
        for alias in cls.FIELD_ALIASES.get(event_key, []):
            if getattr(subscription, alias, None):
                return True
        return False

    @staticmethod
    def _build_context(subscription):
        organization = subscription.organization
        plan_name = subscription.plan.name if subscription.plan_id else 'HRMS Plan'
        expiry_date = subscription.expiry_date.strftime('%d %b %Y') if subscription.expiry_date else 'N/A'
        grace_end = subscription.grace_expires_on
        grace_str = grace_end.strftime('%d %b %Y') if grace_end else 'N/A'
        return {
            'organization_name': organization.name,
            'plan_name': plan_name,
            'expiry_date': expiry_date,
            'grace_end_date': grace_str,
            'renewal_link': RenewalService.build_renewal_url(organization),
            'year': timezone.now().year,
            'company_name': getattr(settings, 'BILLING_COMPANY_NAME', 'PS IntelliHR'),
        }

    @staticmethod
    def _get_smtp_settings(organization):
        if not organization:
            return {}
        from apps.core.models import OrganizationSettings
        qs = (
            OrganizationSettings.all_objects
            if hasattr(OrganizationSettings, 'all_objects')
            else OrganizationSettings.objects
        )
        org_settings = qs.filter(organization=organization).first()
        if not org_settings:
            return {}
        custom = org_settings.custom_settings or {}
        smtp_settings = custom.get('smtp') or {}
        return smtp_settings if isinstance(smtp_settings, dict) else {}

    @staticmethod
    def _resolve_connection(smtp_settings):
        if not smtp_settings or not smtp_settings.get('host'):
            return get_connection()
        backend = smtp_settings.get('backend') or 'django.core.mail.backends.smtp.EmailBackend'
        kw = {
            'host': smtp_settings.get('host'),
            'port': smtp_settings.get('port') or settings.EMAIL_PORT,
            'username': smtp_settings.get('username') or settings.EMAIL_HOST_USER,
            'password': smtp_settings.get('password') or settings.EMAIL_HOST_PASSWORD,
            'timeout': smtp_settings.get('timeout'),
        }
        if smtp_settings.get('use_ssl') is not None:
            kw['use_ssl'] = smtp_settings['use_ssl']
        if smtp_settings.get('use_tls') is not None and not kw.get('use_ssl'):
            kw['use_tls'] = smtp_settings['use_tls']
        kw = {k: v for k, v in kw.items() if v is not None}
        return get_connection(backend=backend, **kw)

    @classmethod
    def _mark_notice(cls, subscription, event_key):
        field_name = cls.FIELD_MAP.get(event_key)
        if not field_name:
            return
        setattr(subscription, field_name, timezone.now())
        subscription.save(update_fields=[field_name, 'updated_at'])
