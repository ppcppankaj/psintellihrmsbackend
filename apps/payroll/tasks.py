"""
Payroll Background Tasks
SECURITY: Tenant-isolated Celery tasks
"""

import io
import logging
from celery import shared_task
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from apps.core.celery_tasks import TenantAwareTask
from apps.payroll.models import PayrollRun, Payslip

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3},
    retry_backoff=True
)
def generate_payroll(self, organization_id: str, payroll_run_id: str):
    """
    Generate payroll for a specific organization only.

    🔒 SECURITY GUARANTEES:
    - Explicit org_id
    - Org filtering enforced
    - Cross-tenant access impossible
    """

    # 🔒 Resolve organization safely
    organization = TenantAwareTask.get_organization(organization_id)

    payroll_run = PayrollRun.objects.filter(
        id=payroll_run_id,
        organization=organization
    ).first()

    if not payroll_run:
        return

    payroll_run.status = PayrollRun.STATUS_PROCESSING
    payroll_run.save(update_fields=['status'])

    from .services import PayrollCalculationService
    PayrollCalculationService.process_payroll_run(payroll_run.id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3},
    retry_backoff=True,
)
def generate_payslip_pdfs_and_notify(self, organization_id: str, payroll_run_id: str):
    """
    On PayrollRun LOCK: Generate PDF payslips and email each employee.

    🔒 SECURITY: Tenant-scoped — only processes payslips belonging to the org.
    """
    organization = TenantAwareTask.get_organization(organization_id)
    if not organization:
        return

    payslips = Payslip.objects.filter(
        payroll_run_id=payroll_run_id,
        payroll_run__organization=organization,
    ).select_related(
        'employee', 'employee__user', 'payroll_run', 'payroll_run__branch',
    )

    for payslip in payslips:
        try:
            _generate_single_payslip_pdf(payslip, organization)
            _notify_employee_payslip(payslip, organization)
        except Exception:
            logger.exception(
                "Payslip PDF/email failed for employee %s (payslip %s)",
                payslip.employee_id,
                payslip.id,
            )


def _generate_single_payslip_pdf(payslip, organization):
    """Generate a PDF payslip using ReportLab and attach to Payslip.pdf_file."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30 * mm, y, organization.name)
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, y, "Payslip")
    y -= 8 * mm

    emp = payslip.employee
    run = payslip.payroll_run
    c.drawString(30 * mm, y, f"Employee: {emp.user.full_name} ({emp.employee_id})")
    y -= 6 * mm
    c.drawString(30 * mm, y, f"Month/Year: {run.month}/{run.year}")
    y -= 6 * mm
    if run.branch:
        c.drawString(30 * mm, y, f"Branch: {run.branch.name}")
        y -= 6 * mm
    y -= 4 * mm

    # Earnings
    c.setFont("Helvetica-Bold", 11)
    c.drawString(30 * mm, y, "Earnings")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    for label, amount in (payslip.earnings_breakdown or {}).items():
        c.drawString(35 * mm, y, f"{label}:")
        c.drawRightString(width - 30 * mm, y, f"{amount}")
        y -= 5 * mm

    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(30 * mm, y, "Deductions")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    for label, amount in (payslip.deductions_breakdown or {}).items():
        c.drawString(35 * mm, y, f"{label}:")
        c.drawRightString(width - 30 * mm, y, f"{amount}")
        y -= 5 * mm

    # Totals
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(30 * mm, y, f"Gross: {payslip.gross_salary}")
    y -= 6 * mm
    c.drawString(30 * mm, y, f"Deductions: {payslip.total_deductions}")
    y -= 6 * mm
    c.drawString(30 * mm, y, f"Net Pay: {payslip.net_salary}")

    c.showPage()
    c.save()

    filename = f"payslip_{emp.employee_id}_{run.month}_{run.year}.pdf"
    payslip.pdf_file.save(filename, ContentFile(buf.getvalue()), save=True)
    buf.close()


def _notify_employee_payslip(payslip, organization):
    """Send payslip notification email to the employee."""
    try:
        from apps.notifications.services.notification_service import NotificationService
    except ImportError:
        logger.warning("NotificationService not available — skipping payslip email")
        return

    emp = payslip.employee
    run = payslip.payroll_run
    NotificationService.notify(
        organization_id=str(organization.id),
        employee=emp,
        subject=f"Payslip ready — {run.month}/{run.year}",
        body=(
            f"Hi {emp.user.first_name},\n\n"
            f"Your payslip for {run.month}/{run.year} is now available. "
            f"Net pay: ₹{payslip.net_salary}.\n\n"
            f"You can download the PDF from your payroll dashboard."
        ),
        channel='email',
    )
