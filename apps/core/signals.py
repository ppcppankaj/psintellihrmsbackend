"""
Audit Signal Handlers - Automatic audit logging for all model changes
"""

import sys
import threading
import logging
from contextlib import contextmanager
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.forms.models import model_to_dict
from django.db import connection
from django.contrib.auth import get_user_model
import json
import uuid

logger = logging.getLogger(__name__)

from .context import get_current_user, get_current_organization, get_client_ip, get_user_agent
from .models import Organization


# Thread-local storage for audit disable flag
_audit_locals = threading.local()


def _is_audit_disabled():
    """Check if audit logging is temporarily disabled"""
    return getattr(_audit_locals, 'disabled', False)


@contextmanager
def disable_audit_signals():
    """Context manager to temporarily disable audit signals"""
    _audit_locals.disabled = True
    try:
        yield
    finally:
        _audit_locals.disabled = False


def _is_running_migrations():
    """Check if we're running migrations"""
    return 'migrate' in sys.argv or 'makemigrations' in sys.argv


def _get_user_if_exists(user):
    """Return user if it exists in the database, else None to avoid FK errors."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(pk=user.pk).exists():
            return user
    except Exception:
        return None

    return None


def _audit_table_exists():
    """Check if audit log table exists in the database"""
    try:
        from django.db import connection, ProgrammingError
        with connection.cursor() as cursor:
            # Check if table exists in active organization
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = current_schema() 
                    AND table_name = 'core_auditlog'
                )
            """)
            return cursor.fetchone()[0]
    except (Exception, ProgrammingError):
        return False



def get_model_changes(instance, old_instance=None):
    """
    Compare old and new instance to get changed fields.
    Returns dict of {field_name: {'old': old_value, 'new': new_value}}
    """
    changes = {}
    
    if old_instance is None:
        # New instance - all fields are "new"
        for field in instance._meta.fields:
            if field.name in ['id', 'created_at', 'updated_at']:
                continue
            value = getattr(instance, field.name)
            if hasattr(value, 'pk'):
                value = str(value.pk)
            elif not isinstance(value, (str, int, float, bool, type(None))):
                value = str(value)
            changes[field.name] = {'old': None, 'new': value}
    else:
        # Compare instances
        for field in instance._meta.fields:
            if field.name in ['id', 'created_at', 'updated_at']:
                continue
            
            old_value = getattr(old_instance, field.name)
            new_value = getattr(instance, field.name)
            
            # Handle foreign keys
            if hasattr(old_value, 'pk'):
                old_value = str(old_value.pk) if old_value else None
            if hasattr(new_value, 'pk'):
                new_value = str(new_value.pk) if new_value else None
            
            # Convert non-serializable types
            if not isinstance(old_value, (str, int, float, bool, type(None))):
                old_value = str(old_value)
            if not isinstance(new_value, (str, int, float, bool, type(None))):
                new_value = str(new_value)
            
            if old_value != new_value:
                changes[field.name] = {'old': old_value, 'new': new_value}
    
    return changes


# Store pre-save state for comparison
_instance_cache = {}


@receiver(pre_save)
def cache_old_instance(sender, instance, **kwargs):
    """Cache the old instance before save for comparison"""
    # Skip if audit signals are disabled
    if _is_audit_disabled():
        return
    
    # Skip during migrations
    if _is_running_migrations():
        return
    
    # Skip audit models and django internal models
    if sender._meta.app_label in ['contenttypes', 'sessions', 'admin', 'auth', 'tenants', 'authentication', 'rbac']:
        return
    
    if sender.__name__ == 'AuditLog':
        return
    
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            _instance_cache[f"{sender.__name__}:{instance.pk}"] = old_instance
        except sender.DoesNotExist:
            pass


@receiver(post_save)
def log_save(sender, instance, created, **kwargs):
    """Log all create/update operations"""
    # Skip if audit signals are disabled
    if _is_audit_disabled():
        return
    
    # Skip during migrations
    if _is_running_migrations():
        return
    
    # Skip audit models and django internal models
    if sender._meta.app_label in ['contenttypes', 'sessions', 'admin', 'auth', 'authentication', 'rbac']:
        return
    
    if sender.__name__ == 'AuditLog':
        return
    
    # Skip if no audit is configured
    if not getattr(sender, '_audit_enabled', True):
        return
    
    # Skip if no organization context is set (optional, depends on policy)
    # if not get_current_organization():
    #     return
    
    # Skip if audit table doesn't exist yet (extra safety)
    if not _audit_table_exists():
        return
    
    try:
        from .models import AuditLog
        
        user = get_current_user()
        org = get_current_organization()

        # Only keep user if it exists in current schema to avoid FK failures
        log_user = _get_user_if_exists(user)
        
        # Get old instance from cache
        cache_key = f"{sender.__name__}:{instance.pk}"
        old_instance = _instance_cache.pop(cache_key, None)
        
        # Get changes
        changes = get_model_changes(instance, old_instance)
        
        if not changes and not created:
            # No actual changes
            return
        
        # Create audit log
        try:
            from django.db import ProgrammingError
            AuditLog.objects.create(
                user=log_user,
                user_email=user.email if user and getattr(user, 'is_authenticated', False) else 'system',
                action='create' if created else 'update',
                resource_type=sender.__name__,
                resource_id=str(instance.pk),
                resource_repr=str(instance)[:500],
                old_values={k: v['old'] for k, v in changes.items()} if not created else {},
                new_values={k: v['new'] for k, v in changes.items()},
                changed_fields=list(changes.keys()),
                ip_address=get_client_ip(),
                user_agent=get_user_agent()[:500] if get_user_agent() else None,
                organization=org,
            )
        except ProgrammingError as e:
            # Table doesn't exist in this schema - common during tenant creation
            if 'relation "core_auditlog" does not exist' in str(e):
                return
            raise e
    except Exception as e:

        # Don't break the app if audit logging fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Audit logging failed: {e}")


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    """Log all delete operations"""
    # Skip if audit signals are disabled
    if _is_audit_disabled():
        return
    
    # Skip during migrations
    if _is_running_migrations():
        return
    
    # Skip audit models and django internal models
    if sender._meta.app_label in ['contenttypes', 'sessions', 'admin', 'auth', 'tenants', 'authentication', 'rbac']:
        return
    
    if sender.__name__ == 'AuditLog':
        return
    
    if not getattr(sender, '_audit_enabled', True):
        return
    
    # Skip if no organization context
    # if not get_current_organization():
    #     return
    
    # Skip if audit table doesn't exist yet (extra safety)
    if not _audit_table_exists():
        return
    
    try:
        from .models import AuditLog
        
        user = get_current_user()
        org = get_current_organization()

        # Only keep user if it exists in current schema to avoid FK failures
        log_user = _get_user_if_exists(user)

        # Get all field values for the deleted instance
        old_values = {}
        for field in instance._meta.fields:
            if field.name in ['id']:
                continue
            value = getattr(instance, field.name)
            if hasattr(value, 'pk'):
                value = str(value.pk)
            elif not isinstance(value, (str, int, float, bool, type(None))):
                value = str(value)
            old_values[field.name] = value
        
        try:
            from django.db import ProgrammingError
            AuditLog.objects.create(
                user=log_user,
                user_email=user.email if user and getattr(user, 'is_authenticated', False) else 'system',
                action='delete',
                resource_type=sender.__name__,
                resource_id=str(instance.pk),
                resource_repr=str(instance)[:500],
                old_values=old_values,
                new_values={},
                changed_fields=[],
                ip_address=get_client_ip(),
                user_agent=get_user_agent()[:500] if get_user_agent() else None,
                organization=org,
            )
        except ProgrammingError as e:
            if 'relation "core_auditlog" does not exist' in str(e):
                return
            raise e
    except Exception as e:

        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Audit logging failed: {e}")


# ---------------------------------------------------------------------------
# Organization bootstrap - auto-create default admin user
# ---------------------------------------------------------------------------

# AUTO-USER CREATION DISABLED
# Users must be created manually via Django admin with organization selection
# This allows creating multiple users per organization

# @receiver(post_save, sender=Organization)
# def create_default_organization_user(sender, instance, created, **kwargs):
#     """
#     DISABLED: Auto-user creation on organization creation.
#     Users are now created manually to allow multiple users per organization.
#     """
#     pass


# ---------------------------------------------------------------------------
# Organization user auto-permissions
# ---------------------------------------------------------------------------

@receiver(post_save, sender='authentication.User')
def auto_set_org_user_permissions(sender, instance, created, **kwargs):
    """
    Auto-set permissions for organization users:
    - If user has an organization, automatically grant staff/verified access
    - No need to manually set groups/permissions
    """
    if not created:
        return
    
    # Skip superusers (they don't need organization)
    if instance.is_superuser:
        return
    
    # If user has organization, auto-enable permissions
    if instance.organization_id:
        update_fields = []
        
        if not instance.is_staff:
            instance.is_staff = True
            update_fields.append('is_staff')
        
        if not instance.is_active:
            instance.is_active = True
            update_fields.append('is_active')
        
        if not instance.is_verified:
            instance.is_verified = True
            update_fields.append('is_verified')
        
        if update_fields:
            User = get_user_model()
            User.objects.filter(pk=instance.pk).update(
                is_staff=instance.is_staff,
                is_active=instance.is_active,
                is_verified=instance.is_verified
            )
            logger.info(
                f"Auto-enabled permissions for org user: {instance.username}",
                extra={
                    "user_id": str(instance.id),
                    "organization_id": str(instance.organization_id),
                    "updated_fields": update_fields
                }
            )


@receiver(post_save, sender=Organization)
def ensure_organization_settings(sender, instance, created, **kwargs):
    """Ensure every organization has a settings row."""
    if not created:
        return

    try:
        from .models import OrganizationSettings

        OrganizationSettings.objects.get_or_create(organization=instance)
    except Exception as exc:  # pragma: no cover - safety only
        logger.warning("Failed to bootstrap organization settings", extra={
            "organization_id": str(instance.id),
            "error": str(exc),
        })

