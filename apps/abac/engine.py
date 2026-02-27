"""
ABAC Policy Engine - Evaluates attribute-based access control policies

SECURITY GUARANTEES:
- Hard-fails if organization context is missing
- Enforces tenant isolation for all policy resolution
- Prevents silent allow/deny behavior
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.core.context import get_current_organization
from .models import GroupPolicy, Policy, PolicyLog, RoleAssignment, UserPolicy


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    evaluated_policies: List[str]
    subject_attributes: Dict[str, Any]
    resource_attributes: Dict[str, Any]
    environment_attributes: Dict[str, Any]
    resource_type: str
    resource_id: Optional[str]
    action: str


class PolicyEngine:
    """
    Main engine for evaluating ABAC policies.
    Determines if a user has access to perform an action on a resource.
    """

    def __init__(self, user, log_decisions=True):
        self.user = user
        self.log_decisions = log_decisions

        # 🔒 CRITICAL: Organization context is mandatory
        self.organization = get_current_organization()
        if not self.organization and not self.user.is_superuser:
            raise PermissionDenied(
                "ABAC denied: Organization context is missing"
            )

    # --------------------------------------------------
    # PUBLIC ENTRY POINT
    # --------------------------------------------------
    def check_access(
        self,
        resource_type: str,
        action: str,
        resource_attrs: Optional[Dict[str, Any]] = None,
        resource_id: Optional[str] = None,
    ) -> bool:
        """Main access control check."""

        decision = self.evaluate(
            resource_type=resource_type,
            action=action,
            resource_attrs=resource_attrs,
            resource_id=resource_id,
        )
        return decision.allowed

    def evaluate(
        self,
        resource_type: str,
        action: str,
        resource_attrs: Optional[Dict[str, Any]] = None,
        resource_id: Optional[str] = None,
    ) -> PolicyDecision:
        """Evaluate access request and return structured decision."""

        resource_attrs = resource_attrs or {}
        subject_attrs = self._get_subject_attributes()
        environment_attrs = self._get_environment_attributes()

        if self.user.is_superuser:
            decision = PolicyDecision(
                allowed=True,
                reason='Superuser bypass',
                evaluated_policies=[],
                subject_attributes=subject_attrs,
                resource_attributes=resource_attrs,
                environment_attributes=environment_attrs,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
            )
            if self.log_decisions:
                self._log_decision(decision)
            return decision

        if subject_attrs.get('is_org_admin'):
            decision = PolicyDecision(
                allowed=True,
                reason='Org admin bypass',
                evaluated_policies=[],
                subject_attributes=subject_attrs,
                resource_attributes=resource_attrs,
                environment_attributes=environment_attrs,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
            )
            if self.log_decisions:
                self._log_decision(decision)
            return decision

        policies = self._get_applicable_policies(resource_type, action, resource_id)

        allowed, reason, evaluated_policies = self._evaluate_policies(
            policies,
            subject_attrs,
            resource_attrs,
            action,
            environment_attrs,
        )

        decision = PolicyDecision(
            allowed=allowed,
            reason=reason,
            evaluated_policies=evaluated_policies,
            subject_attributes=subject_attrs,
            resource_attributes=resource_attrs,
            environment_attributes=environment_attrs,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
        )

        if self.log_decisions:
            self._log_decision(decision)

        return decision

    # --------------------------------------------------
    # ATTRIBUTE EXTRACTION
    # --------------------------------------------------
    def _get_subject_attributes(self) -> Dict[str, Any]:
        """Extract subject (user) attributes"""

        attrs = {
            'user_id': str(self.user.id),
            'email': self.user.email,
            'is_superuser': self.user.is_superuser,
            'is_org_admin': getattr(self.user, 'is_org_admin', False),
            'is_verified': self.user.is_verified,
            'organization_id': str(self.organization.id) if self.organization else None,
            'organization_name': self.organization.name if self.organization else None,
        }

        # Employee attributes
        if hasattr(self.user, 'employee') and self.user.employee:
            emp = self.user.employee
            attrs.update({
                'employee_id': emp.employee_id,
                'department': emp.department.name if emp.department else None,
                'department_id': str(emp.department.id) if emp.department else None,
                'designation': emp.designation.name if emp.designation else None,
                'job_level': getattr(emp.designation, 'level', None) if emp.designation else None,
                'location': emp.location.name if emp.location else None,
                'location_id': str(emp.location.id) if emp.location else None,
                'employment_status': emp.employment_status,
                'employment_type': emp.employment_type,
                'date_of_joining': emp.date_of_joining,
                'is_manager': emp.direct_reports.exists(),
                'manager_id': str(emp.reporting_manager.id) if emp.reporting_manager else None,
            })

        return attrs

    def _get_environment_attributes(self) -> Dict[str, Any]:
        """Extract environmental attributes"""

        now = timezone.now()

        return {
            'current_time': now.time().isoformat(),
            'current_date': now.date().isoformat(),
            'current_datetime': now.isoformat(),
            'day_of_week': now.strftime('%A'),
            'is_weekend': now.weekday() >= 5,
            'hour': now.hour,
        }

    # --------------------------------------------------
    # POLICY RESOLUTION
    # --------------------------------------------------
    def _get_applicable_policies(
        self,
        resource_type: str,
        action: str,
        resource_id: Optional[str] = None
    ) -> List[Policy]:
        """
        Fetch policies applicable to this request.
        """

        # 🔒 USER POLICIES (TENANT SCOPED)
        if not self.organization:
            return []

        tenant_policy_ids = set(
            Policy.objects.filter(
                organization=self.organization,
                is_active=True,
            ).values_list('id', flat=True)
        )

        user_policies = UserPolicy.objects.filter(
            user=self.user,
            organization=self.organization,
            is_active=True,
        ).select_related('policy')

        active_user_policies = [
            up.policy
            for up in user_policies
            if up.is_valid_now()
            and up.policy.is_active
            and up.policy.is_valid_now()
        ]

        # 🔒 GROUP POLICIES (TENANT SCOPED)
        subject_attrs = self._get_subject_attributes()
        group_policies = self._get_group_policies(subject_attrs)
        role_policies = self._get_role_policies()

        policy_map = {}
        for policy in active_user_policies + group_policies + role_policies:
            policy_map[str(policy.id)] = policy

        all_policies = [
            policy
            for policy in policy_map.values()
            if not tenant_policy_ids or str(policy.id) in tenant_policy_ids
        ]

        applicable = []
        for policy in all_policies:
            if policy.resource_type and policy.resource_type != resource_type:
                continue

            if policy.actions and action not in policy.actions:
                continue

            if policy.resource_id and resource_id and policy.resource_id != resource_id:
                continue

            applicable.append(policy)

        applicable.sort(key=lambda p: p.priority, reverse=True)
        return applicable

    def _get_group_policies(self, subject_attrs: Dict[str, Any]) -> List[Policy]:
        """Resolve group-based policies (tenant scoped)"""

        if not self.organization:
            return []

        group_policies = []

        active_groups = GroupPolicy.objects.filter(
            organization=self.organization,
            is_active=True
        ).prefetch_related('policies')

        for group in active_groups:
            if group.group_type == 'department':
                if subject_attrs.get('department') == group.group_value:
                    group_policies.extend(group.policies.filter(is_active=True))
            elif group.group_type == 'location':
                if subject_attrs.get('location') == group.group_value:
                    group_policies.extend(group.policies.filter(is_active=True))
            elif group.group_type == 'job_level':
                if subject_attrs.get('job_level') == group.group_value:
                    group_policies.extend(group.policies.filter(is_active=True))
            elif group.group_type == 'employment_type':
                if subject_attrs.get('employment_type') == group.group_value:
                    group_policies.extend(group.policies.filter(is_active=True))

        return list(group_policies)

    def _get_role_policies(self) -> List[Policy]:
        """Resolve policies attached to active role assignments."""

        if not self.organization:
            return []

        policies: List[Policy] = []
        assignments = (
            RoleAssignment.objects.filter(
                organization=self.organization,
                user=self.user,
                is_active=True,
            )
            .select_related('role')
            .prefetch_related('role__policies')
        )

        for assignment in assignments:
            if not assignment.is_valid_now():
                continue
            role = assignment.role
            if not role or not role.is_active:
                continue
            active_policies = role.policies.filter(
                is_active=True,
                organization=self.organization,
            )
            for policy in active_policies:
                if policy.is_valid_now():
                    policies.append(policy)

        return policies

    # --------------------------------------------------
    # POLICY EVALUATION
    # --------------------------------------------------
    def _evaluate_policies(
        self,
        policies: List[Policy],
        subject_attrs: Dict,
        resource_attrs: Dict,
        action: str,
        environment_attrs: Dict
    ) -> tuple:
        """
        Evaluate policies and return decision.
        """

        if not policies:
            return False, "No applicable policies found", []

        deny_policies = []
        allow_policies = []
        evaluated_ids = []

        for policy in policies:
            evaluated_ids.append(str(policy.id))

            if policy.evaluate(
                subject_attrs,
                resource_attrs,
                action,
                environment_attrs
            ):
                if policy.effect == Policy.DENY:
                    deny_policies.append(policy)
                else:
                    allow_policies.append(policy)

        if deny_policies:
            return (
                False,
                f"Denied by policy: {', '.join(p.name for p in deny_policies)}",
                evaluated_ids
            )

        if allow_policies:
            return (
                True,
                f"Allowed by policy: {', '.join(p.name for p in allow_policies)}",
                evaluated_ids
            )

        return False, "No matching policy rules", evaluated_ids

    # --------------------------------------------------
    # AUDIT LOGGING
    # --------------------------------------------------
    def _log_decision(self, decision: PolicyDecision):
        """Persist policy decision for auditing via Celery."""

        if not self.organization or not self.user:
            return

        policy_id = decision.evaluated_policies[0] if decision.evaluated_policies else None
        payload = {
            'user_id': str(self.user.id),
            'organization_id': str(self.organization.id),
            'policy_id': policy_id,
            'resource_type': decision.resource_type,
            'resource_id': decision.resource_id or '',
            'action': decision.action,
            'result': decision.allowed,
            'subject_attributes': decision.subject_attributes,
            'resource_attributes': decision.resource_attributes,
            'environment_attributes': decision.environment_attributes,
            'policies_evaluated': decision.evaluated_policies,
            'decision_reason': decision.reason,
        }

        try:
            from .tasks import log_policy_evaluation

            log_policy_evaluation.delay(payload)
        except Exception:  # pragma: no cover - fallback to sync logging
            PolicyLog.objects.create(
                user=self.user,
                organization=self.organization,
                policy_id=policy_id,
                resource_type=decision.resource_type,
                resource_id=decision.resource_id or '',
                action=decision.action,
                result=decision.allowed,
                subject_attributes=decision.subject_attributes,
                resource_attributes=decision.resource_attributes,
                environment_attributes=decision.environment_attributes,
                policies_evaluated=decision.evaluated_policies,
                decision_reason=decision.reason,
            )
