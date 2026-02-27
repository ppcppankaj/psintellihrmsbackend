"""Template rendering utilities for notifications"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from django.template import Context, Engine

from apps.notifications.models import NotificationTemplate


@dataclass
class RenderedNotification:
    """Structured result of template rendering."""
    subject: str
    body: str
    missing_variables: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


class TemplateRenderer:
    """Render notification templates with safe defaults."""

    def __init__(self) -> None:
        self.engine = Engine(autoescape=True)

    def render(self, template: NotificationTemplate, context: Dict[str, Any] | None = None) -> RenderedNotification:
        context = context or {}
        missing_vars = [var for var in (template.variables or []) if var not in context]
        safe_context: Dict[str, Any] = {**context}
        for var in missing_vars:
            safe_context.setdefault(var, '')

        subject_template = self.engine.from_string(template.subject)
        body_template = self.engine.from_string(template.body)

        rendered_subject = subject_template.render(Context(safe_context)).strip()
        rendered_body = body_template.render(Context(safe_context)).strip()

        return RenderedNotification(
            subject=rendered_subject,
            body=rendered_body,
            missing_variables=missing_vars,
            context=context,
        )
