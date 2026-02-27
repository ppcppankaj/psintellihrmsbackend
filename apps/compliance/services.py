"""Compliance services: audit exports and retention enforcement"""
from io import BytesIO
from typing import Dict, List
from django.utils import timezone
from django.db.models import Q
from django.core.files.base import ContentFile

import pandas as pd

from apps.core.models import AuditLog
from .models import DataRetentionPolicy, AuditExportRequest, RetentionExecution


class AuditExportService:
    """Generate audit exports based on filters"""

    @staticmethod
    def run_export(export_request: AuditExportRequest, user):
        export_request.status = AuditExportRequest.STATUS_RUNNING
        export_request.started_at = timezone.now()
        export_request.save(update_fields=['status', 'started_at'])

        try:
            qs = AuditLog.objects.all()
            org = user.get_organization() if hasattr(user, 'get_organization') else None
            if org:
                qs = qs.filter(organization_id=str(org.id))

            filters = export_request.filters or {}
            if filters.get('action'):
                qs = qs.filter(action=filters['action'])
            if filters.get('resource_type'):
                qs = qs.filter(resource_type=filters['resource_type'])
            if filters.get('user_email'):
                qs = qs.filter(user_email__icontains=filters['user_email'])
            if filters.get('date_from'):
                qs = qs.filter(timestamp__gte=filters['date_from'])
            if filters.get('date_to'):
                qs = qs.filter(timestamp__lte=filters['date_to'])

            data = list(qs.values())
            df = pd.DataFrame(data)

            format_choice = filters.get('format', 'csv')
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')

            if format_choice == 'xlsx':
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                buffer.seek(0)
                export_request.file.save(
                    f"audit_export_{timestamp}.xlsx",
                    ContentFile(buffer.read()),
                    save=False
                )
            else:
                csv_bytes = df.to_csv(index=False).encode('utf-8')
                export_request.file.save(
                    f"audit_export_{timestamp}.csv",
                    ContentFile(csv_bytes),
                    save=False
                )

            export_request.row_count = len(data)
            export_request.status = AuditExportRequest.STATUS_COMPLETED
        except Exception as exc:
            export_request.status = AuditExportRequest.STATUS_FAILED
            export_request.error_message = str(exc)
        finally:
            export_request.completed_at = timezone.now()
            export_request.save()

        return export_request


class RetentionService:
    """Retention enforcement based on policies"""

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

    @classmethod
    def run_execution(cls, execution: RetentionExecution, user=None):
        execution.status = RetentionExecution.STATUS_RUNNING
        execution.started_at = timezone.now()
        execution.save(update_fields=['status', 'started_at'])

        try:
            policy = execution.policy
            model = cls._resolve_model(policy.entity_type)

            qs = model.objects.all()
            qs = cls._apply_org_filter(qs, user, execution.policy.organization)
            qs = cls._apply_policy_filters(qs, policy)

            cutoff = timezone.now() - timezone.timedelta(days=policy.retention_days)
            date_field = policy.date_field or 'created_at'
            if cls._has_field(model, date_field):
                qs = qs.filter(**{f"{date_field}__lt": cutoff})

            affected_count = qs.count()

            details = {
                'entity_type': policy.entity_type,
                'cutoff': cutoff.isoformat(),
                'action': policy.action,
                'sample_ids': list(qs.values_list('id', flat=True)[:25]),
            }

            if not execution.dry_run:
                cls._apply_action(qs, policy.action)

            execution.affected_count = affected_count
            execution.details = details
            execution.status = RetentionExecution.STATUS_COMPLETED
        except Exception as exc:
            execution.status = RetentionExecution.STATUS_FAILED
            execution.error_message = str(exc)
        finally:
            execution.completed_at = timezone.now()
            execution.save()

        return execution

    @classmethod
    def _resolve_model(cls, entity_type: str):
        if entity_type not in cls.ALLOWED_MODEL_MAP:
            raise ValueError(f"Unsupported entity_type: {entity_type}")
        module_path, class_name = cls.ALLOWED_MODEL_MAP[entity_type]
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)

    @staticmethod
    def _has_field(model, field_name: str) -> bool:
        return any(field.name == field_name for field in model._meta.get_fields())

    @classmethod
    def _apply_org_filter(cls, queryset, user, policy_org=None):
        if user and getattr(user, 'is_superuser', False):
            return queryset
        org = None
        if user and hasattr(user, 'get_organization'):
            org = user.get_organization()
        if not org and policy_org:
            org = policy_org
        if org and cls._has_field(queryset.model, 'organization'):
            return queryset.filter(organization=org)
        return queryset

    @classmethod
    def _apply_policy_filters(cls, queryset, policy: DataRetentionPolicy):
        filters = policy.filter_criteria or {}
        for key, value in filters.items():
            if isinstance(value, list):
                queryset = queryset.filter(**{f"{key}__in": value})
            else:
                queryset = queryset.filter(**{key: value})
        return queryset

    @classmethod
    def _apply_action(cls, queryset, action: str):
        model = queryset.model
        now = timezone.now()
        if action == 'archive':
            if cls._has_field(model, 'is_active'):
                queryset.update(is_active=False)
            return
        if action == 'delete':
            if cls._has_field(model, 'is_deleted'):
                queryset.update(is_deleted=True, deleted_at=now)
            return
        if action == 'anonymize':
            for obj in queryset.iterator():
                cls._anonymize_instance(obj)
            return

    @classmethod
    def _anonymize_instance(cls, obj):
        pii_fields = ['first_name', 'last_name', 'email', 'phone', 'mobile', 'name']
        updated = False
        for field in obj._meta.fields:
            if field.name in pii_fields:
                if field.null:
                    setattr(obj, field.name, None)
                else:
                    setattr(obj, field.name, 'REDACTED')
                updated = True

        if hasattr(obj, 'metadata') and isinstance(getattr(obj, 'metadata', None), dict):
            obj.metadata['anonymized'] = True
            updated = True

        if hasattr(obj, 'is_active'):
            obj.is_active = False
            updated = True

        if hasattr(obj, 'is_deleted'):
            obj.is_deleted = True
            obj.deleted_at = timezone.now()
            updated = True

        if updated:
            obj.save()
