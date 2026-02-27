"""
Razorpay Webhook Handler — Server-to-Server Payment Verification

Validates the webhook signature using RAZORPAY_WEBHOOK_SECRET, then
processes payment.authorized / payment.captured / payment.failed events.

Endpoint: POST /api/v1/billing/webhook/razorpay/
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.billing.models import PaymentTransaction

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class RazorpayWebhookView(View):
    """
    Receives Razorpay webhook events.

    Expected headers:
      X-Razorpay-Signature: <HMAC-SHA256 of body with webhook secret>

    Supported events:
      - payment.authorized
      - payment.captured
      - payment.failed
    """

    http_method_names = ["post"]

    def post(self, request):
        # 1. Verify signature
        signature = request.headers.get("X-Razorpay-Signature", "")
        webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")

        if not webhook_secret:
            logger.error("razorpay_webhook_no_secret configured")
            return JsonResponse({"error": "Webhook not configured"}, status=500)

        body = request.body
        if not self._verify_signature(body, signature, webhook_secret):
            logger.warning("razorpay_webhook_signature_invalid")
            return JsonResponse({"error": "Invalid signature"}, status=400)

        # 2. Parse payload
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        event = payload.get("event", "")
        entity = (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )

        logger.info(
            "razorpay_webhook event=%s payment_id=%s order_id=%s",
            event,
            entity.get("id"),
            entity.get("order_id"),
        )

        # 3. Dispatch event
        handler = {
            "payment.authorized": self._handle_authorized,
            "payment.captured": self._handle_captured,
            "payment.failed": self._handle_failed,
        }.get(event)

        if handler:
            try:
                handler(entity)
            except Exception:
                logger.exception("razorpay_webhook_handler_error event=%s", event)
                return JsonResponse({"error": "Processing error"}, status=500)

        return JsonResponse({"status": "ok"})

    # ── Signature verification ───────────────────────────────────────────

    @staticmethod
    def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ── Event handlers ───────────────────────────────────────────────────

    def _handle_authorized(self, entity: dict):
        """Payment authorized — update transaction status."""
        self._update_transaction(
            entity, status=PaymentTransaction.STATUS_CREATED
        )

    def _handle_captured(self, entity: dict):
        """Payment captured — mark as success and activate subscription."""
        order_id = entity.get("order_id", "")
        payment_id = entity.get("id", "")

        try:
            txn = PaymentTransaction.objects.select_related(
                "organization", "plan"
            ).get(razorpay_order_id=order_id)
        except PaymentTransaction.DoesNotExist:
            logger.warning(
                "razorpay_webhook_txn_not_found order_id=%s", order_id
            )
            return

        if txn.status == PaymentTransaction.STATUS_SUCCESS:
            logger.info("razorpay_webhook_already_processed order_id=%s", order_id)
            return

        txn.razorpay_payment_id = payment_id
        txn.status = PaymentTransaction.STATUS_SUCCESS
        txn.save(update_fields=["razorpay_payment_id", "status", "updated_at"])

        # Activate subscription via existing service
        try:
            from apps.billing.services import SubscriptionService
            SubscriptionService.activate_subscription(
                organization=txn.organization,
                plan=txn.plan,
            )
            logger.info(
                "razorpay_webhook_subscription_activated org=%s plan=%s",
                txn.organization_id,
                txn.plan.code,
            )
        except Exception:
            logger.exception(
                "razorpay_webhook_activation_failed org=%s", txn.organization_id
            )

    def _handle_failed(self, entity: dict):
        """Payment failed — mark transaction as failed."""
        self._update_transaction(
            entity, status=PaymentTransaction.STATUS_FAILED
        )

    @staticmethod
    def _update_transaction(entity: dict, status: str):
        order_id = entity.get("order_id", "")
        payment_id = entity.get("id", "")

        updated = PaymentTransaction.objects.filter(
            razorpay_order_id=order_id
        ).update(
            razorpay_payment_id=payment_id,
            status=status,
        )

        if not updated:
            logger.warning(
                "razorpay_webhook_txn_not_found order_id=%s", order_id
            )
