"""
RBAC Hardening Module — Enterprise Multi-Tenant Security
=========================================================

Centralised enforcement layer for:
  S1  — TenantScopedQuerysetMixin (strict queryset isolation)
  S2  — SuperuserLeakageGuard (block superuser visibility)
  S3  — Role-tier DRF permission classes
  S4  — SelfOnlyMixin (reject foreign employee_id)
  S5  — TenantFKValidator (cross-tenant FK linking prevention)
  S9  — OrganizationRateThrottle (per-tenant rate limit)
  S10 — AuditLogger (security-event audit trail)
"""

import logging
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# S1 — TENANT-SCOPED QUERYSET MIXIN
# ═══════════════════════════════════════════════════════════════════════════

class TenantScopedQuerysetMixin:
    """
    Strict queryset isolation for ALL org-scoped ViewSets.

    Rules
    -----
    • Superuser  → full queryset (``Model.objects.all()``)
    • Org member → ``Model.objects.filter(organization=request.organization)``
    • No org context + not superuser → empty queryset

    NEVER trusts frontend ``X-Organization-ID`` header.
    NEVER allows ``?organization_id=`` query-param filtering.
    """

    def get_queryset(self):
        qs = super().get_queryset()

        # Swagger / schema generation guard
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        user = self.request.user

        # Superuser: organisation context is optional (global view)
        if user.is_superuser:
            org = getattr(self.request, 'organization', None)
            if org and hasattr(qs.model, 'organization_id'):
                return qs.filter(organization=org)
            return qs

        # Non-superuser MUST have org context resolved by middleware
        org = getattr(self.request, 'organization', None)
        if not org:
            return qs.none()

        if hasattr(qs.model, 'organization_id'):
            return qs.filter(organization=org)

        # Model has no organization field — return empty for safety
        return qs.none()

    def perform_create(self, serializer):
        """Auto-inject organisation on create (non-superuser)."""
        org = getattr(self.request, 'organization', None)
        if not org and not self.request.user.is_superuser:
            raise PermissionDenied('Organization context required.')

        kwargs = {}
        model = serializer.Meta.model
        if hasattr(model, 'organization_id') and org:
            kwargs['organization'] = org
        if hasattr(model, 'created_by_id'):
            kwargs['created_by'] = self.request.user
        serializer.save(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# S2 — SUPERUSER LEAKAGE GUARD
# ═══════════════════════════════════════════════════════════════════════════

class SuperuserLeakageGuardMixin:
    """
    Prevents superuser records from appearing in org-scoped user lists.

    Apply to **UserViewSet** (or any viewset exposing ``User`` objects).
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.is_superuser:
            return qs  # Superadmin sees everything

        # Strip superusers from non-superadmin views
        return qs.filter(is_superuser=False)

    def check_object_permissions(self, request, obj):
        """Block PATCH / DELETE targeting a superuser by non-superuser."""
        super().check_object_permissions(request, obj)

        if request.method in ('PATCH', 'PUT', 'DELETE'):
            if getattr(obj, 'is_superuser', False) and not request.user.is_superuser:
                raise PermissionDenied(
                    'Non-superusers cannot modify or delete superuser accounts.'
                )

    def perform_update(self, serializer):
        """Prevent role downgrade of superuser by non-superuser."""
        instance = serializer.instance
        user = self.request.user

        if not user.is_superuser:
            # Block any attempt to touch privilege fields on a superuser
            if getattr(instance, 'is_superuser', False):
                raise PermissionDenied(
                    'Cannot modify superuser accounts.'
                )

            # Block elevation attempts
            dangerous_fields = {'is_superuser', 'is_staff', 'is_org_admin'}
            changed = set(serializer.validated_data.keys()) & dangerous_fields
            if changed:
                raise PermissionDenied(
                    'Only superusers can modify privilege levels.'
                )

        serializer.save()


# ═══════════════════════════════════════════════════════════════════════════
# S3 — ROLE-TIER PERMISSION CLASSES
# ═══════════════════════════════════════════════════════════════════════════

class IsSuperAdmin(BasePermission):
    """Access restricted to platform superusers only."""
    message = 'Superadmin access required.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsOrganizationAdmin(BasePermission):
    """
    Access for org admins (is_staff / is_org_admin) within their org.
    Superusers are implicitly allowed.
    """
    message = 'Organization admin access required.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        # NOTE: is_staff is auto-set for ALL org users by signal.
        # Only is_org_admin distinguishes admins from regular users.
        return bool(
            getattr(user, 'is_org_admin', False)
        ) and bool(getattr(request, 'organization', None))

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        org = getattr(request, 'organization', None)
        if not org:
            return False
        obj_org_id = getattr(obj, 'organization_id', None)
        if obj_org_id and str(obj_org_id) != str(org.id):
            return False
        return bool(getattr(user, 'is_org_admin', False))


class IsOrganizationUser(BasePermission):
    """
    Access for regular org users (not superuser, not staff/org_admin).
    Typically used to restrict to self-only endpoints.
    """
    message = 'Organization user access required.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # Must NOT be superuser and NOT org_admin.
        # NOTE: is_staff is auto-set for ALL org users by signal, so it
        # cannot be used to distinguish regular users from admins.
        return bool(
            not user.is_superuser
            and not getattr(user, 'is_org_admin', False)
            and getattr(request, 'organization', None)
        )


# ═══════════════════════════════════════════════════════════════════════════
# S4 — SELF-ONLY ENDPOINT MIXIN
# ═══════════════════════════════════════════════════════════════════════════

class SelfOnlyMixin:
    """
    For endpoints like /my-attendance/, /my-leave/, /my-payslips/.

    NEVER accepts ``employee_id`` from request body.
    Always enforces ``employee = request.user.employee``.
    If mismatch → 403.
    """

    def get_employee_from_request(self, request):
        """Resolve the authenticated user's employee record."""
        employee = getattr(request.user, 'employee', None)
        if not employee:
            from apps.employees.models import Employee
            org = getattr(request, 'organization', None)
            qs = Employee.objects.filter(user=request.user)
            if org:
                qs = qs.filter(organization=org)
            employee = qs.first()
        return employee

    def enforce_self_only(self, request, data=None):
        """
        Validate that request body does NOT contain an ``employee_id``
        or ``employee`` field that differs from the caller's own record.

        Returns the caller's employee instance.
        Raises PermissionDenied on mismatch.
        """
        employee = self.get_employee_from_request(request)
        if not employee:
            raise PermissionDenied('No employee profile found for current user.')

        if data is None:
            data = request.data

        # Check for employee_id injection
        submitted_id = data.get('employee_id') or data.get('employee')
        if submitted_id:
            submitted_str = str(submitted_id)
            if submitted_str != str(employee.id) and submitted_str != str(employee.employee_id):
                raise PermissionDenied(
                    'You may only access your own records. '
                    'Employee ID mismatch detected.'
                )

        return employee

    def get_queryset(self):
        """Restrict queryset to own records for non-privileged users."""
        qs = super().get_queryset()
        user = self.request.user

        if user.is_superuser:
            return qs
        if getattr(user, 'is_org_admin', False) or user.is_staff:
            return qs  # Org admins can see all within their org

        employee = self.get_employee_from_request(self.request)
        if not employee:
            return qs.none()

        if hasattr(qs.model, 'employee_id'):
            return qs.filter(employee=employee)
        if hasattr(qs.model, 'user_id'):
            return qs.filter(user=self.request.user)
        return qs.none()


# ═══════════════════════════════════════════════════════════════════════════
# S5 — FK TENANT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TenantFKValidatorMixin:
    """
    Serializer mixin that validates ALL FK fields referencing
    OrganizationEntity models belong to ``request.organization``.

    Prevents cross-tenant FK linking.
    """

    # Subclasses may list FK fields to validate explicitly
    tenant_fk_fields = None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if not request:
            return attrs

        org = getattr(request, 'organization', None)
        if not org:
            return attrs

        # If superuser, skip FK validation (they can operate cross-org)
        if request.user.is_superuser:
            return attrs

        fields_to_check = self.tenant_fk_fields or self._auto_detect_fk_fields()

        for field_name in fields_to_check:
            value = attrs.get(field_name)
            if value is None:
                continue

            # Value could be model instance or UUID
            if hasattr(value, 'organization_id'):
                if value.organization_id and str(value.organization_id) != str(org.id):
                    raise ValidationError({
                        field_name: f'Invalid {field_name}: belongs to a different organization.'
                    })
            elif hasattr(value, 'organization'):
                fk_org = getattr(value, 'organization', None)
                if fk_org and hasattr(fk_org, 'id') and str(fk_org.id) != str(org.id):
                    raise ValidationError({
                        field_name: f'Invalid {field_name}: belongs to a different organization.'
                    })

        return attrs

    def _auto_detect_fk_fields(self):
        """
        Auto-detect FK fields that point to OrganizationEntity subclasses.
        """
        from apps.core.models import OrganizationEntity

        detected = []
        model = getattr(self.Meta, 'model', None)
        if not model:
            return detected

        for field in model._meta.get_fields():
            if hasattr(field, 'related_model') and field.related_model:
                if issubclass(field.related_model, OrganizationEntity):
                    detected.append(field.name)

        return detected


# ═══════════════════════════════════════════════════════════════════════════
# S9 — PER-TENANT RATE THROTTLE
# ═══════════════════════════════════════════════════════════════════════════

class OrganizationRateThrottle(SimpleRateThrottle):
    """
    Throttle requests per organization (tenant).

    Superusers are exempt (return ``None`` cache key).
    All other users share a bucket keyed by ``org.id``.
    """

    scope = 'org'
    rate = '1000/hour'  # Sensible default; override via DEFAULT_THROTTLE_RATES

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return self.get_ident(request)

        if request.user.is_superuser:
            return None  # No throttle for superadmin

        org = getattr(request, 'organization', None)
        if not org:
            return self.get_ident(request)  # Fallback to IP

        return f'throttle_{self.scope}_{org.id}'


# ═══════════════════════════════════════════════════════════════════════════
# S10 — AUDIT LOGGER
# ═══════════════════════════════════════════════════════════════════════════

class AuditLogger:
    """
    Centralised security audit logger.

    Records high-value events to the ``AuditLog`` model:
      • Role changes
      • Permission updates
      • Payroll lock
      • Plan upgrades
      • Superuser creation
      • Feature flag toggles
      • Cross-tenant access attempts
    """

    @staticmethod
    def log(
        *,
        action: str,
        actor,
        organization=None,
        entity_type: str = '',
        entity_id: str = '',
        metadata: dict = None,
        request=None,
    ):
        """
        Write an audit entry.

        Parameters
        ----------
        action : str
            E.g. ``'role_change'``, ``'payroll_lock'``, ``'superuser_created'``
        actor : User
            The user performing the action.
        organization : Organization, optional
            Target org (defaults to request.organization).
        entity_type : str
            E.g. ``'User'``, ``'PayrollRun'``, ``'FeatureFlag'``
        entity_id : str
            PK of the affected entity.
        metadata : dict
            Arbitrary JSON payload (old_values, new_values, etc.).
        request : HttpRequest, optional
            For extracting IP / user-agent.
        """
        from apps.core.models import AuditLog

        if not organization and request:
            organization = getattr(request, 'organization', None)

        ip_address = None
        user_agent = None
        request_id = None

        if request:
            ip_address = (
                request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                or request.META.get('REMOTE_ADDR')
            )
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            request_id = getattr(request, 'request_id', None)

        try:
            AuditLog.objects.create(
                organization=organization,
                user=actor,
                user_email=getattr(actor, 'email', ''),
                action=action,
                resource_type=entity_type,
                resource_id=str(entity_id) if entity_id else '',
                new_values=metadata or {},
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
        except Exception:
            logger.exception('Failed to write audit log entry: %s', action)

    # ── Convenience methods ──────────────────────────────────────────────

    @classmethod
    def log_role_change(cls, *, actor, target_user, old_roles, new_roles, request=None):
        cls.log(
            action='role_change',
            actor=actor,
            entity_type='User',
            entity_id=str(target_user.id),
            metadata={
                'target_email': target_user.email,
                'old_roles': old_roles,
                'new_roles': new_roles,
            },
            request=request,
        )

    @classmethod
    def log_permission_update(cls, *, actor, target, changes, request=None):
        cls.log(
            action='permission_update',
            actor=actor,
            entity_type=type(target).__name__,
            entity_id=str(target.id) if hasattr(target, 'id') else '',
            metadata={'changes': changes},
            request=request,
        )

    @classmethod
    def log_payroll_lock(cls, *, actor, payroll_run, request=None):
        cls.log(
            action='payroll_lock',
            actor=actor,
            organization=payroll_run.organization,
            entity_type='PayrollRun',
            entity_id=str(payroll_run.id),
            metadata={
                'month': payroll_run.month,
                'year': payroll_run.year,
                'status': payroll_run.status,
            },
            request=request,
        )

    @classmethod
    def log_plan_upgrade(cls, *, actor, subscription, old_plan, new_plan, request=None):
        cls.log(
            action='plan_upgrade',
            actor=actor,
            organization=subscription.organization,
            entity_type='OrganizationSubscription',
            entity_id=str(subscription.id),
            metadata={
                'old_plan': str(old_plan),
                'new_plan': str(new_plan),
            },
            request=request,
        )

    @classmethod
    def log_superuser_creation(cls, *, actor, new_superuser, request=None):
        cls.log(
            action='superuser_created',
            actor=actor,
            entity_type='User',
            entity_id=str(new_superuser.id),
            metadata={'email': new_superuser.email},
            request=request,
        )

    @classmethod
    def log_feature_flag_toggle(cls, *, actor, flag, old_state, new_state, request=None):
        cls.log(
            action='feature_flag_toggle',
            actor=actor,
            organization=flag.organization,
            entity_type='FeatureFlag',
            entity_id=str(flag.id),
            metadata={
                'flag_name': flag.name,
                'old_enabled': old_state,
                'new_enabled': new_state,
            },
            request=request,
        )

    @classmethod
    def log_cross_tenant_attempt(cls, *, actor, target_org_id, resource, request=None):
        cls.log(
            action='cross_tenant_attempt',
            actor=actor,
            entity_type=type(resource).__name__ if resource else 'Unknown',
            entity_id=str(resource.id) if hasattr(resource, 'id') else '',
            metadata={'attempted_org_id': str(target_org_id)},
            request=request,
        )
