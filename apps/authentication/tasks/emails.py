from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 5, "countdown": 30},
    acks_late=True,
)
def send_email_task(subject, text, html, to_email):
    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        email.attach_alternative(html, "text/html")
        email.send()

        logger.info("Email sent successfully", extra={"to": to_email})

    except Exception as exc:
        logger.exception("Email sending failed", extra={"to": to_email})
        raise exc
