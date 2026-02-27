"""
Organization Context Management (Async-Safe)
Uses contextvars instead of threading.local for async compatibility
"""

from contextvars import ContextVar
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Context variables (async-safe)
current_organization_var: ContextVar = ContextVar('current_organization', default=None)
current_user_var: ContextVar = ContextVar('current_user', default=None)
current_branch_var: ContextVar = ContextVar('current_branch', default=None)
client_ip_var: ContextVar = ContextVar('client_ip', default=None)
user_agent_var: ContextVar = ContextVar('user_agent', default=None)
device_id_var: ContextVar = ContextVar('device_id', default=None)


def get_current_organization():
    """Get current organization from context."""
    return current_organization_var.get()


def set_current_organization(organization) -> None:
    """Set current organization in context."""
    current_organization_var.set(organization)


def get_current_user():
    """Get current user from context."""
    return current_user_var.get()


def set_current_user(user) -> None:
    """Set current user in context."""
    current_user_var.set(user)


def get_current_branch():
    """Get current branch from context."""
    return current_branch_var.get()


def set_current_branch(branch) -> None:
    """Set current branch in context."""
    current_branch_var.set(branch)


def get_client_ip():
    """Get client IP from context."""
    return client_ip_var.get()


def set_client_ip(ip: str) -> None:
    """Set client IP in context."""
    client_ip_var.set(ip)


def get_user_agent():
    """Get user agent from context."""
    return user_agent_var.get()


def set_user_agent(ua: str) -> None:
    """Set user agent in context."""
    user_agent_var.set(ua)


def get_device_id():
    """Get device ID from context."""
    return device_id_var.get()


def set_device_id(device_id: str) -> None:
    """Set device ID in context."""
    device_id_var.set(device_id)


def clear_context() -> None:
    """
    Clear all context variables.
    Called at the end of each request.
    """
    set_current_organization(None)
    set_current_user(None)
    set_current_branch(None)
    set_client_ip(None)
    set_user_agent(None)
    set_device_id(None)
