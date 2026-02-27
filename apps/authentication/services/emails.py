from django.template.loader import render_to_string
from apps.authentication.tasks.emails import send_email_task


def send_password_reset_email(user, reset_url):
    subject = "Reset your HRMS password"

    context = {
        "user": user,
        "reset_url": reset_url,
        "expiry_minutes": 30,
        "company_name": "HRMS",
        "year": 2026,
    }

    text = render_to_string("emails/password_reset.txt", context)
    html = render_to_string("emails/password_reset.html", context)

    send_email_task.delay(
        subject=subject,
        text=text,
        html=html,
        to_email=user.email,
    )
