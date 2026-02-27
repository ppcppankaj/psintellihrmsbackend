"""Report execution services"""
from io import BytesIO
from typing import Dict, List, Tuple
from django.utils import timezone
from django.db.models import Q
from django.core.files.base import ContentFile

import pandas as pd

from .models import ReportTemplate, ReportExecution


class ReportExecutionService:
    """Service layer for report execution"""

    ALLOWED_MODEL_MAP = {
        'employees': ('apps.employees.models', 'Employee'),
        'attendance_records': ('apps.attendance.models', 'AttendanceRecord'),
        'leave_requests': ('apps.leave.models', 'LeaveRequest'),
        'payroll_runs': ('apps.payroll.models', 'PayrollRun'),
        'payslips': ('apps.payroll.models', 'Payslip'),
        'assets': ('apps.assets.models', 'Asset'),
        'expense_claims': ('apps.expenses.models', 'ExpenseClaim'),
        'job_applications': ('apps.recruitment.models', 'JobApplication'),
    }

    @staticmethod
    def get_template(template_id=None, template_code=None, user=None):
        queryset = ReportTemplate.objects.all()
        if user and not user.is_superuser and hasattr(user, 'get_organization'):
            org = user.get_organization()
            if org:
                queryset = queryset.filter(organization=org)

        if template_id:
            return queryset.filter(id=template_id).first()
        if template_code:
            return queryset.filter(code=template_code).first()
        return None

    @staticmethod
    def create_execution(template, requested_by, output_format, filters, parameters):
        org = requested_by.get_organization() if hasattr(requested_by, 'get_organization') else None
        execution = ReportExecution.objects.create(
            template=template,
            template_code=template.code if template else '',
            template_name=template.name if template else '',
            requested_by=requested_by,
            organization=org,
            output_format=output_format or ReportExecution.FORMAT_CSV,
            filters=filters or {},
            parameters=parameters or {},
            status=ReportExecution.STATUS_PENDING,
        )
        return execution

    @staticmethod
    def enqueue_execution(execution_id):
        from .tasks import run_report_execution
        run_report_execution.delay(str(execution_id))

    @classmethod
    def run_execution(cls, execution: ReportExecution, user):
        start_time = timezone.now()
        execution.status = ReportExecution.STATUS_RUNNING
        execution.started_at = start_time
        execution.save(update_fields=['status', 'started_at'])

        try:
            data, columns = cls._build_data(execution.template, user, execution.filters, execution.parameters)
            content, filename = cls._render_report(data, columns, execution.output_format)

            execution.file.save(filename, ContentFile(content), save=False)
            execution.file_size = len(content)
            execution.columns = columns
            execution.row_count = len(data)
            execution.status = ReportExecution.STATUS_COMPLETED
        except Exception as exc:
            execution.status = ReportExecution.STATUS_FAILED
            execution.error_message = str(exc)
        finally:
            execution.completed_at = timezone.now()
            execution.execution_time_ms = int((execution.completed_at - start_time).total_seconds() * 1000)
            execution.save()

        return execution

    @classmethod
    def _build_data(cls, template: ReportTemplate, user, filters: Dict, parameters: Dict) -> Tuple[List[Dict], List[str]]:
        if not template:
            raise ValueError("Template is required")

        query_config = template.query_config or {}
        model_key = query_config.get('model') or template.report_type

        model = cls._resolve_model(model_key, query_config.get('model_path'))
        queryset = model.objects.all()

        queryset = cls._apply_org_filter(queryset, user)
        queryset = cls._apply_branch_filter(queryset, user)
        filter_payload = dict(filters or {})
        queryset = cls._apply_filters(queryset, model, template, filter_payload, query_config)

        columns = query_config.get('columns') or template.columns
        if not columns:
            columns = [field.name for field in model._meta.fields]

        safe_columns = cls._safe_columns(model, columns)
        data = list(queryset.values(*safe_columns)) if safe_columns else list(queryset.values())
        return data, safe_columns or list(data[0].keys()) if data else []

    @classmethod
    def _resolve_model(cls, model_key: str, model_path: str = None):
        if model_path:
            module_path, class_name = model_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            return getattr(module, class_name)

        if not model_key:
            raise ValueError("Report template missing model configuration")

        if model_key not in cls.ALLOWED_MODEL_MAP:
            raise ValueError(f"Model '{model_key}' is not allowed for reporting")

        module_path, class_name = cls.ALLOWED_MODEL_MAP[model_key]
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)

    @staticmethod
    def _has_field(model, field_name: str) -> bool:
        return any(field.name == field_name for field in model._meta.get_fields())

    @classmethod
    def _apply_org_filter(cls, queryset, user):
        if user and getattr(user, 'is_superuser', False):
            return queryset

        org = None
        if user and hasattr(user, 'get_organization'):
            org = user.get_organization()
        if org and cls._has_field(queryset.model, 'organization'):
            return queryset.filter(organization=org)
        return queryset

    @classmethod
    def _apply_branch_filter(cls, queryset, user):
        if not user:
            return queryset
        if user.is_superuser or user.is_org_admin or user.is_organization_admin():
            return queryset

        branch_ids = cls._get_branch_ids(user)
        if not branch_ids:
            return queryset.none()

        model = queryset.model
        if cls._has_field(model, 'branch'):
            return queryset.filter(branch_id__in=branch_ids)
        if cls._has_field(model, 'employee'):
            return queryset.filter(employee__branch_id__in=branch_ids)
        if cls._has_field(model, 'current_assignee'):
            return queryset.filter(current_assignee__branch_id__in=branch_ids)
        if cls._has_field(model, 'assigned_to'):
            return queryset.filter(assigned_to__branch_id__in=branch_ids)
        return queryset

    @staticmethod
    def _get_branch_ids(user) -> List[str]:
        branch_ids = []
        try:
            from apps.authentication.models_hierarchy import BranchUser
            branch_ids = list(
                BranchUser.objects.filter(user=user, is_active=True).values_list('branch_id', flat=True)
            )
        except Exception:
            branch_ids = []

        if not branch_ids and hasattr(user, 'employee'):
            employee = user.employee
            if employee and employee.branch_id:
                branch_ids = [employee.branch_id]
        return branch_ids

    @classmethod
    def _apply_filters(cls, queryset, model, template: ReportTemplate, filters: Dict, query_config: Dict):
        allowed_filters = set(template.filters or [])
        allowed_filters.update(query_config.get('allowed_filters', []))
        filter_map = query_config.get('filter_map', {})

        date_from = filters.pop('date_from', None)
        date_to = filters.pop('date_to', None)
        search_term = filters.pop('search', None) or filters.pop('q', None)

        for key, value in list(filters.items()):
            field_name = filter_map.get(key, key)
            if allowed_filters and field_name not in allowed_filters:
                continue

            if isinstance(value, list):
                queryset = queryset.filter(**{f"{field_name}__in": value})
            else:
                queryset = queryset.filter(**{field_name: value})

        date_field = query_config.get('date_field', 'created_at')
        if (date_from or date_to) and cls._has_field(model, date_field):
            if date_from:
                queryset = queryset.filter(**{f"{date_field}__gte": date_from})
            if date_to:
                queryset = queryset.filter(**{f"{date_field}__lte": date_to})

        search_fields = query_config.get('search_fields', [])
        if search_term and search_fields:
            q = Q()
            for field in search_fields:
                q |= Q(**{f"{field}__icontains": search_term})
            queryset = queryset.filter(q)

        return queryset

    @classmethod
    def _safe_columns(cls, model, columns: List[str]) -> List[str]:
        safe = []
        for col in columns:
            if '__' in col:
                root = col.split('__', 1)[0]
                if cls._has_field(model, root):
                    safe.append(col)
            else:
                if cls._has_field(model, col):
                    safe.append(col)
        return safe

    @classmethod
    def _render_report(cls, data: List[Dict], columns: List[str], output_format: str):
        if not columns and data:
            columns = list(data[0].keys())

        df = pd.DataFrame(data, columns=columns or None)
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')

        if output_format == ReportExecution.FORMAT_XLSX:
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            buffer.seek(0)
            return buffer.read(), f"report_{timestamp}.xlsx"

        if output_format == ReportExecution.FORMAT_PDF:
            return cls._render_pdf(df, timestamp), f"report_{timestamp}.pdf"

        # Default CSV
        csv_data = df.to_csv(index=False)
        return csv_data.encode('utf-8'), f"report_{timestamp}.csv"

    @staticmethod
    def _render_pdf(df: pd.DataFrame, timestamp: str) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"Report Export {timestamp}", styles['Title']))
        elements.append(Spacer(1, 12))

        data = [list(df.columns)] + df.astype(str).values.tolist()
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(table)
        doc.build(elements)
        buffer.seek(0)
        return buffer.read()
