"""Invoice generation service"""
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from apps.billing.models import Invoice, OrganizationBillingProfile

logger = logging.getLogger(__name__)


class InvoiceService:
    """Handles GST invoice creation and PDF generation."""

    GST_PERCENTAGE = Decimal('18.00')
    PAYMENT_DUE_DAYS = 7

    @classmethod
    def create_paid_invoice(cls, *, organization, subscription, plan, transaction=None):
        """Create a paid invoice with GST computation."""
        if not plan or plan.monthly_price is None:
            raise ValidationError('Plan pricing missing for invoice generation.')

        amount = Decimal(plan.monthly_price)
        gst_amount = (amount * cls.GST_PERCENTAGE / Decimal('100')).quantize(Decimal('0.01'))
        total_amount = (amount + gst_amount).quantize(Decimal('0.01'))

        profile = OrganizationBillingProfile.objects.filter(organization=organization).first()
        billing_name = (profile.legal_name if profile and profile.legal_name else organization.name)
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
        logger.info('Invoice %s created for %s (total=%s)', invoice.invoice_number, organization, total_amount)
        return invoice

    @classmethod
    def create_renewal_invoice(cls, *, organization, subscription, plan):
        """Create an unpaid invoice for renewal (payment pending)."""
        if not plan or plan.monthly_price is None:
            raise ValidationError('Plan pricing missing for invoice generation.')

        amount = Decimal(plan.monthly_price)
        gst_amount = (amount * cls.GST_PERCENTAGE / Decimal('100')).quantize(Decimal('0.01'))
        total_amount = (amount + gst_amount).quantize(Decimal('0.01'))

        profile = OrganizationBillingProfile.objects.filter(organization=organization).first()
        billing_name = (profile.legal_name if profile and profile.legal_name else organization.name)
        billing_address = (profile.billing_address if profile else '') or getattr(organization, 'address', '') or ''
        gstin = (profile.gstin if profile else '') or ''

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
            paid_status=Invoice.STATUS_PENDING,
        )
        cls.generate_pdf(invoice)
        return invoice

    @staticmethod
    def _generate_invoice_number():
        today_str = timezone.now().strftime('%Y%m%d')
        suffix = uuid.uuid4().hex[:6].upper()
        return f"INV-{today_str}-{suffix}"

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
        """Render and attach the GST invoice PDF."""
        try:
            from weasyprint import HTML
        except ImportError:
            logger.warning('WeasyPrint not installed – skipping PDF for %s', invoice.invoice_number)
            return

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
