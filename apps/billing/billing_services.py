"""Subscription services and helpers"""
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import (
    Invoice,
    OrganizationBillingProfile,
    OrganizationSubscription,
    Plan,
)
from apps.core.models import OrganizationSettings

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Utility helpers for plan and subscription enforcement"""

    DEFAULT_TRIAL_DAYS = 14

    @classmethod
    def get_active_subscription(cls, organization):
        if not organization:
            return None
        return (
            OrganizationSubscription.objects.select_related('plan')
            .filter(organization=organization, is_active=True)
            .order_by('-start_date')
            .first()
        )

    # ------------------------------------------------------------------
    # Capacity enforcement
    # ------------------------------------------------------------------
    @classmethod
    def ensure_employee_capacity(cls, organization):
        subscription = cls._require_active_subscription(organization)
        max_employees = subscription.plan.max_employees
        if not max_employees:
            return subscription

        from apps.employees.models import Employee

        active_employees = Employee.objects.filter(
            organization=organization,
            is_deleted=False,
        ).count()
        if active_employees >= max_employees:
            raise ValidationError(
                f"Employee limit reached ({max_employees}). Upgrade your plan to add more employees."
            )
        return subscription

    @classmethod
    def ensure_branch_capacity(cls, organization):
        subscription = cls._require_active_subscription(organization)
        max_branches = subscription.plan.max_branches
        if not max_branches:
            return subscription

        from apps.authentication.models_hierarchy import Branch

        branch_count = Branch.objects.filter(organization=organization).count()
        if branch_count >= max_branches:
            raise ValidationError(
                f"Branch limit reached ({max_branches}). Upgrade your plan to add more branches."
            )
        return subscription

    @classmethod
    def ensure_storage_available(cls, organization, new_file_size):
        subscription = cls._require_active_subscription(organization)
        storage_limit = subscription.plan.storage_limit
        if not storage_limit:
            return subscription

        limit_bytes = int(Decimal(storage_limit) * Decimal(1024 * 1024))
        from apps.employees.models import Document
        from apps.onboarding.models import OnboardingDocument

        document_usage = (
            Document.objects.filter(organization=organization)
            .aggregate(total=Sum('file_size'))
            .get('total')
            or 0
        )
        onboarding_usage = (
            OnboardingDocument.objects.filter(organization=organization)
            .aggregate(total=Sum('file_size'))
            .get('total')
            or 0
        )
        current_usage = document_usage + onboarding_usage
        projected = current_usage + int(new_file_size or 0)
        if projected > limit_bytes:
            raise ValidationError(
                "Storage limit exceeded for your current plan. Delete unused documents or upgrade your plan."
            )
        return subscription

    # ------------------------------------------------------------------
    # Feature enforcement
    # ------------------------------------------------------------------
    @classmethod
    def ensure_feature_enabled(cls, organization, feature_flag):
        subscription = cls._require_active_subscription(organization)
        is_enabled = getattr(subscription.plan, feature_flag, True)
        if not is_enabled:
            raise PermissionDenied("This feature is not available on your current subscription plan.")
        return subscription

    # ------------------------------------------------------------------
    # Trial management
    # ------------------------------------------------------------------
    @classmethod
    def auto_assign_trial(cls, organization):
        if OrganizationSubscription.objects.filter(organization=organization).exists():
            return None

        plan = cls.get_default_plan()
        if not plan:
            return None

        start_date = timezone.now().date()
        trial_end = start_date + timedelta(days=cls.DEFAULT_TRIAL_DAYS)
        subscription = OrganizationSubscription.objects.create(
            organization=organization,
            plan=plan,
            start_date=start_date,
            expiry_date=trial_end,
            trial_end_date=trial_end,
            is_trial=True,
        )
        return subscription

    @staticmethod
    def get_default_plan():
        return Plan.objects.filter(is_active=True).order_by('monthly_price').first()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @classmethod
    def _require_active_subscription(cls, organization):
        subscription = cls.get_active_subscription(organization)
        if not subscription:
            raise ValidationError("No active subscription found for this organization.")
        return subscription

    @classmethod
    def deactivate_if_expired(cls, subscription):
        if not subscription or not subscription.is_active:
            return False
        if subscription.is_trial and subscription.trial_end_date:
            today = timezone.now().date()
            if today > subscription.trial_end_date:
                subscription.deactivate()
                return True
        if RenewalService.has_grace_passed(subscription):
            subscription.deactivate(reason='grace_period_ended')
            return True
        return False

    @classmethod
    def activate_paid_subscription(cls, organization, plan, duration_days=30):
        if not organization or not plan:
            raise ValidationError("Organization and plan are required for activation.")

        start_date = timezone.now().date()
        expiry_date = start_date + timedelta(days=duration_days)

        with db_transaction.atomic():
            active_subscriptions = (
                OrganizationSubscription.objects.select_for_update()
                .filter(organization=organization, is_active=True)
            )
            for subscription in active_subscriptions:
                subscription.deactivate(reason='replaced_by_payment')

            new_subscription = OrganizationSubscription.objects.create(
                organization=organization,
                plan=plan,
                start_date=start_date,
                expiry_date=expiry_date,
                trial_end_date=None,
                is_trial=False,
                is_active=True,
                grace_period_days=OrganizationSubscription.GRACE_PERIOD_DEFAULT,
            )

        return new_subscription


class RenewalService:
    """Handles subscription expiry reminders and grace logic."""

    REMINDER_3_DAYS = 3
    REMINDER_1_DAY = 1

    @classmethod
    def build_renewal_url(cls, organization):
        base_url = getattr(settings, 'BILLING_PORTAL_BASE_URL', '') or ''
        base_url = base_url.rstrip('/')
        if not organization:
            return ''
        if base_url:
            return f"{base_url}/billing/renew/{organization.id}"
        return f"/billing/renew/{organization.id}"

    @classmethod
    def process_subscription(cls, subscription):
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
        desired_status = 'trial' if subscription.is_trial else 'active'
        if org.subscription_status != desired_status:
            org.subscription_status = desired_status
            org.save(update_fields=['subscription_status', 'updated_at'])

    @staticmethod
    def _enqueue_email_task(event_key, subscription_id):
        if not subscription_id:
            return
        try:
            from .tasks import (
                send_expiry_3_day_email,
                send_expiry_1_day_email,
                send_expired_email,
                send_grace_email,
                send_suspended_email,
            )
        except Exception:  # pragma: no cover - defensive
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
    """Renders and sends subscription reminder emails via Celery."""

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

        queryset = (
            OrganizationSubscription.all_objects
            if hasattr(OrganizationSubscription, 'all_objects')
            else OrganizationSubscription.objects
        )
        subscription = (
            subscription
            or queryset.select_related('organization', 'plan').filter(id=subscription_id).first()
        )
        if not subscription or not subscription.organization_id:
            logger.warning('Subscription %s not found for %s email', subscription_id, event_key)
            return False

        organization = subscription.organization
        recipient = getattr(organization, 'email', None)
        if not recipient:
            logger.info('Organization %s has no billing email; skipping %s notice', organization, event_key)
            return False

        subject = cls.SUBJECT_MAP.get(event_key, 'Subscription update').format(
            plan=subscription.plan.name if subscription.plan_id else 'HRMS',
        )
        context = cls._build_context(subscription)
        template_name = cls.TEMPLATE_MAP[event_key]
        html_body = render_to_string(template_name, context)
        text_body = strip_tags(html_body)

        smtp_settings = cls._get_smtp_settings(organization)
        from_email = smtp_settings.get('from_email') or settings.DEFAULT_FROM_EMAIL
        connection = cls._resolve_connection(smtp_settings)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[recipient],
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
        queryset = (
            OrganizationSettings.all_objects
            if hasattr(OrganizationSettings, 'all_objects')
            else OrganizationSettings.objects
        )
        org_settings = queryset.filter(organization=organization).first()
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
        connection_kwargs = {
            'host': smtp_settings.get('host'),
            'port': smtp_settings.get('port') or settings.EMAIL_PORT,
            'username': smtp_settings.get('username') or settings.EMAIL_HOST_USER,
            'password': smtp_settings.get('password') or settings.EMAIL_HOST_PASSWORD,
            'timeout': smtp_settings.get('timeout'),
        }

        use_ssl = smtp_settings.get('use_ssl')
        use_tls = smtp_settings.get('use_tls')
        if use_ssl is not None:
            connection_kwargs['use_ssl'] = use_ssl
        if use_tls is not None and not connection_kwargs.get('use_ssl'):
            connection_kwargs['use_tls'] = use_tls

        connection_kwargs = {k: v for k, v in connection_kwargs.items() if v is not None}
        return get_connection(backend=backend, **connection_kwargs)

    @classmethod
    def _mark_notice(cls, subscription, event_key):
        field_name = cls.FIELD_MAP.get(event_key)
        if not field_name:
            return
        setattr(subscription, field_name, timezone.now())
        subscription.save(update_fields=[field_name, 'updated_at'])


class InvoiceService:
    """Handles GST invoice generation"""

    GST_PERCENTAGE = Decimal('18.00')
    PAYMENT_DUE_DAYS = 7

    @classmethod
    def create_paid_invoice(cls, *, organization, subscription, plan, transaction=None):
        if not plan or plan.monthly_price is None:
            raise ValidationError("Plan pricing missing for invoice generation.")

        amount = Decimal(plan.monthly_price)
        gst_amount = (amount * cls.GST_PERCENTAGE / Decimal('100')).quantize(Decimal('0.01'))
        total_amount = (amount + gst_amount).quantize(Decimal('0.01'))

        profile = OrganizationBillingProfile.objects.filter(organization=organization).first()
        billing_name = profile.legal_name if profile and profile.legal_name else organization.name
        billing_address = ''
        if profile and profile.billing_address:
            billing_address = profile.billing_address
        else:
            billing_address = getattr(organization, 'address', '') or ''
        gstin = profile.gstin if profile and profile.gstin else ''

        invoice = Invoice.objects.create(
            organization=organization,
            subscription=subscription,
            plan=plan,
            invoice_number=cls._generate_invoice_number(),
            amount=amount,
            gst_percentage=cls.GST_PERCENTAGE,
            gst_amount=gst_amount,
            total_amount=total_amount,
            billing_name=billing_name,
            billing_address=billing_address,
            gstin=gstin,
            due_date=timezone.now().date() + timedelta(days=cls.PAYMENT_DUE_DAYS),
            paid_status=Invoice.STATUS_PAID,
            paid_at=timezone.now(),
        )

        cls.generate_pdf(invoice, transaction)
        return invoice

    @staticmethod
    def _generate_invoice_number():
        today = timezone.now().strftime('%Y%m%d')
        suffix = uuid.uuid4().hex[:6].upper()
        return f"INV-{today}-{suffix}"

    @staticmethod
    def _company_context():
        return {
            'name': getattr(settings, 'BILLING_COMPANY_NAME', 'PS IntelliHR'),
            'gstin': getattr(settings, 'BILLING_COMPANY_GSTIN', ''),
            'address': getattr(settings, 'BILLING_COMPANY_ADDRESS', ''),
            'logo_url': getattr(settings, 'BILLING_COMPANY_LOGO_URL', ''),
        }

    @classmethod
    def generate_pdf(cls, invoice, transaction=None):
        try:
            from weasyprint import HTML
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise ValidationError('PDF generation requires WeasyPrint.') from exc

        context = {
            'invoice': invoice,
            'subscription': invoice.subscription,
            'organization': invoice.organization,
            'plan': invoice.plan,
            'transaction': transaction,
            'company': cls._company_context(),
        }

        html = render_to_string('billing/gst_invoice.html', context)
        pdf_bytes = HTML(string=html, base_url=settings.BASE_DIR).write_pdf()
        filename = f"{invoice.invoice_number}.pdf"
        invoice.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)