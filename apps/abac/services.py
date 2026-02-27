"""ABAC service orchestrating tenant-safe policy evaluation."""

from typing import Dict, Optional

from django.core.exceptions import PermissionDenied

from apps.core.context import get_current_organization

from .engine import PolicyDecision, PolicyEngine


class ABACService:
    """Facade that wraps PolicyEngine and enforces tenant-aware evaluation."""

    @staticmethod
    def evaluate_access(
        user,
        resource_type: str,
        action: str,
        resource_id: Optional[str] = None,
        resource_attributes: Optional[Dict[str, object]] = None,
        log_decision: bool = True,
    ) -> PolicyDecision:
        """Evaluate whether a user may perform an action on a resource."""

        organization = get_current_organization()
        if not organization and not getattr(user, 'is_superuser', False):
            raise PermissionDenied('Organization context required for ABAC evaluation.')

        engine = PolicyEngine(user, log_decisions=log_decision)
        return engine.evaluate(
            resource_type=resource_type,
            action=action,
            resource_attrs=resource_attributes,
            resource_id=resource_id,
        )
