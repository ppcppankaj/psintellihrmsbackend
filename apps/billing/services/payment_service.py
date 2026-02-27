"""Razorpay payment flow orchestration"""
import logging
from decimal import Decimal

import razorpay
from razorpay.errors import SignatureVerificationError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.billing.models import Invoice, PaymentTransaction

logger = logging.getLogger(__name__)


class PaymentService:
    """Handles Razorpay order creation, signature verification, and post-payment bookkeeping."""

    # ------------------------------------------------------------------
    # Razorpay client
    # ------------------------------------------------------------------
    @staticmethod
    def _get_client():
        key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
        if not key_id or not key_secret:
            raise ValidationError('Razorpay keys are not configured. Contact support.')
        return razorpay.Client(auth=(key_id, key_secret))

    # ------------------------------------------------------------------
    # Create order
    # ------------------------------------------------------------------
    @classmethod
    def create_order(cls, *, organization, plan):
        """
        1. Create a Razorpay order
        2. Persist a ``PaymentTransaction(status=created)``
        3. Return ``(transaction, razorpay_order_dict)``
        """
        if not organization:
            raise ValidationError('Organization context is required to create an order.')
        if not plan or not plan.is_active:
            raise ValidationError('A valid active plan is required.')

        amount = plan.monthly_price
        if amount is None or amount <= 0:
            raise ValidationError('Plan price must be greater than zero.')

        currency = getattr(settings, 'RAZORPAY_CURRENCY', 'INR')
        amount_paise = int((Decimal(amount) * Decimal('100')).quantize(Decimal('1')))

        client = cls._get_client()
        order_payload = {
            'amount': amount_paise,
            'currency': currency,
            'payment_capture': 1,
            'notes': {
                'organization_id': str(organization.id),
                'plan_code': plan.code,
            },
        }
        order = client.order.create(order_payload)

        transaction = PaymentTransaction.objects.create(
            organization=organization,
            plan=plan,
            amount=amount,
            currency=currency,
            status=PaymentTransaction.STATUS_CREATED,
            razorpay_order_id=order.get('id', ''),
            metadata={'order': order},
        )

        logger.info('Razorpay order %s created for org=%s plan=%s',
                     order.get('id'), organization.id, plan.code)
        return transaction, order

    # ------------------------------------------------------------------
    # Verify payment
    # ------------------------------------------------------------------
    @classmethod
    @db_transaction.atomic
    def verify_and_activate(cls, *, organization, razorpay_order_id,
                            razorpay_payment_id, razorpay_signature):
        """
        1. Verify Razorpay signature
        2. Mark transaction SUCCESS
        3. Activate paid subscription
        4. Create paid invoice
        Returns ``(transaction, subscription, invoice)``
        """
        try:
            transaction = PaymentTransaction.objects.select_related('plan').get(
                razorpay_order_id=razorpay_order_id,
                organization=organization,
            )
        except PaymentTransaction.DoesNotExist as exc:
            raise ValidationError('Payment transaction not found for this order.') from exc

        # Idempotency guard
        if transaction.status == PaymentTransaction.STATUS_SUCCESS and transaction.subscription_id:
            from .subscription_service import SubscriptionService
            sub = SubscriptionService.get_active_subscription(organization)
            invoice = Invoice.objects.filter(
                organization=organization,
                subscription=sub,
            ).order_by('-generated_at').first()
            return transaction, sub, invoice

        # Signature verification
        client = cls._get_client()
        params = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        }
        try:
            client.utility.verify_payment_signature(params)
        except SignatureVerificationError as exc:
            transaction.status = PaymentTransaction.STATUS_FAILED
            meta = transaction.metadata or {}
            meta['verification_error'] = str(exc)
            transaction.metadata = meta
            transaction.save(update_fields=['status', 'metadata', 'updated_at'])
            raise ValidationError('Payment verification failed. Retry the transaction.') from exc

        # Mark transaction success
        transaction.razorpay_payment_id = razorpay_payment_id
        transaction.razorpay_signature = razorpay_signature
        transaction.status = PaymentTransaction.STATUS_SUCCESS
        transaction.paid_at = timezone.now()
        meta = transaction.metadata or {}
        meta['verification_payload'] = params
        transaction.metadata = meta
        transaction.save(update_fields=[
            'razorpay_payment_id', 'razorpay_signature',
            'status', 'paid_at', 'metadata', 'updated_at',
        ])

        # Activate subscription
        from .subscription_service import SubscriptionService
        subscription = SubscriptionService.activate_paid_subscription(
            organization, transaction.plan
        )
        transaction.subscription = subscription
        transaction.save(update_fields=['subscription', 'updated_at'])

        # Create invoice
        from .invoice_service import InvoiceService
        invoice = InvoiceService.create_paid_invoice(
            organization=organization,
            subscription=subscription,
            plan=transaction.plan,
            transaction=transaction,
        )

        logger.info('Payment verified and subscription activated: org=%s plan=%s',
                     organization.id, transaction.plan.code)
        return transaction, subscription, invoice
