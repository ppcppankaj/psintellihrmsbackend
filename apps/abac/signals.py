"""
ABAC Signals - Cache invalidation and Session invalidation on role/permission changes

CRITICAL SECURITY FEATURE:
When user roles or permissions change, all their active sessions and tokens
are invalidated to force re-authentication with updated permissions.
"""

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.sessions.models import Session
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# SESSION INVALIDATION ON ROLE CHANGES
# ============================================================================

@receiver(post_save, sender='abac.RoleAssignment')
def invalidate_sessions_on_role_assignment(sender, instance, created, **kwargs):
    """
    Invalidate all user sessions when a role is assigned or modified.
    Forces user to re-authenticate with new permissions.
    """
    _invalidate_user_sessions(
        user=instance.user,
        reason=f"Role {'assigned' if created else 'modified'}: {instance.role.name}"
    )


@receiver(post_delete, sender='abac.RoleAssignment')
def invalidate_sessions_on_role_removal(sender, instance, **kwargs):
    """
    Invalidate all user sessions when a role is removed.
    Prevents privilege escalation after role revocation.
    """
    _invalidate_user_sessions(
        user=instance.user,
        reason=f"Role removed: {instance.role.name}"
    )


@receiver(post_save, sender='authentication.BranchUser')
def invalidate_sessions_on_branch_access_change(sender, instance, created, **kwargs):
    """
    Invalidate sessions when branch access changes.
    User might have switched to a branch they no longer have access to.
    """
    if not created:
        # Only on updates (active status change)
        _invalidate_user_sessions(
            user=instance.user,
            reason=f"Branch access modified: {instance.branch.name}"
        )


@receiver(post_delete, sender='authentication.BranchUser')
def invalidate_sessions_on_branch_removal(sender, instance, **kwargs):
    """
    Invalidate sessions when branch access is revoked.
    Clears any session that had that branch selected.
    """
    _invalidate_user_sessions(
        user=instance.user,
        reason=f"Branch access revoked: {instance.branch.name}",
        branch_id=str(instance.branch_id)
    )


@receiver(pre_save, sender='authentication.User')
def store_old_admin_status(sender, instance, **kwargs):
    """Store old is_org_admin value for comparison after save"""
    if instance.pk:
        try:
            User = sender
            old_instance = User.objects.get(pk=instance.pk)
            instance._old_is_org_admin = old_instance.is_org_admin
        except sender.DoesNotExist:
            instance._old_is_org_admin = None


@receiver(post_save, sender='authentication.User')
def invalidate_sessions_on_admin_demotion(sender, instance, created, **kwargs):
    """
    Invalidate sessions when user is demoted from org admin.
    Critical for preventing privilege escalation.
    """
    if created:
        return
    
    old_is_admin = getattr(instance, '_old_is_org_admin', None)
    if old_is_admin is not None and old_is_admin and not instance.is_org_admin:
        _invalidate_user_sessions(
            user=instance,
            reason="Demoted from organization admin"
        )


def _invalidate_user_sessions(user, reason, branch_id=None):
    """
    Core function to invalidate all sessions and tokens for a user.
    
    Args:
        user: User object whose sessions should be invalidated
        reason: String describing why sessions are being invalidated
        branch_id: Optional - only clear sessions with this branch selected
    """
    logger.info(f"Invalidating sessions for user {user.id}: {reason}")
    
    # 1. Invalidate UserSession records (if model exists)
    try:
        from apps.authentication.models import UserSession
        
        if branch_id:
            # Only invalidate sessions with this specific branch
            sessions = UserSession.objects.filter(
                user=user,
                is_active=True
            )
            for session in sessions:
                try:
                    session_data = session.session.get_decoded()
                    if session_data.get('current_branch_id') == branch_id:
                        session.is_active = False
                        session.save()
                        logger.info(f"Invalidated session {session.id} (branch: {branch_id})")
                except Exception:
                    # If we can't decode, invalidate anyway to be safe
                    session.is_active = False
                    session.save()
        else:
            # Invalidate all user sessions
            count = UserSession.objects.filter(
                user=user,
                is_active=True
            ).update(is_active=False)
            logger.info(f"Invalidated {count} sessions for user {user.id}")
            
    except ImportError:
        logger.warning("UserSession model not found, skipping session invalidation")
    except Exception as e:
        logger.error(f"Error invalidating UserSession: {e}")
    
    # 2. Blacklist JWT refresh tokens
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            OutstandingToken, BlacklistedToken
        )
        
        outstanding_tokens = OutstandingToken.objects.filter(user=user)
        for token in outstanding_tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                pass  # Token might already be blacklisted
        
        logger.info(f"Blacklisted {outstanding_tokens.count()} tokens for user {user.id}")
        
    except ImportError:
        logger.warning("JWT token blacklist not available")
    except Exception as e:
        logger.error(f"Error blacklisting tokens: {e}")
    
    # 3. Clear Django session data
    try:
        from django.contrib.sessions.models import Session
        from django.contrib.auth import get_user_model
        
        # Get all sessions and check which belong to this user
        # This is expensive but necessary for security
        sessions = Session.objects.filter(expire_date__gte=timezone.now())
        deleted_count = 0
        
        for session in sessions:
            try:
                data = session.get_decoded()
                if str(data.get('_auth_user_id')) == str(user.pk):
                    session.delete()
                    deleted_count += 1
            except Exception:
                pass  # Skip sessions we can't decode
        
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} Django sessions for user {user.id}")
            
    except Exception as e:
        logger.error(f"Error clearing Django sessions: {e}")
    
    # 4. Create audit log entry
    try:
        from apps.core.models import AuditLog
        
        AuditLog.objects.create(
            user=user,
            user_email=user.email,
            organization=getattr(user, 'organization', None),
            action='session_invalidation',
            resource_type='User',
            resource_id=str(user.id),
            resource_repr=user.email,
            old_values={},
            new_values={'reason': reason},
            changed_fields=['session'],
            ip_address='system',
            user_agent='ABAC Security Signal'
        )
        
    except Exception as e:
        logger.warning(f"Could not create audit log: {e}")


# ============================================================================
# CACHE INVALIDATION ON POLICY CHANGES
# ============================================================================

@receiver(post_save, sender='abac.UserPolicy')
@receiver(post_delete, sender='abac.UserPolicy')
def invalidate_user_policy_cache(sender, instance, **kwargs):
    """Invalidate cache when user policies change"""
    try:
        from apps.core.permission_cache import PermissionCache
        PermissionCache.invalidate_user_all(instance.user_id)
    except ImportError:
        pass
    
    # Also invalidate sessions for immediate effect
    _invalidate_user_sessions(
        user=instance.user,
        reason=f"Policy changed: {instance.policy.name}"
    )


@receiver(post_save, sender='abac.PolicyRule')
@receiver(post_delete, sender='abac.PolicyRule')
def invalidate_policy_rule_cache(sender, instance, **kwargs):
    """Invalidate cache when policy rules change"""
    try:
        from apps.core.permission_cache import PermissionCache
        from apps.abac.models import UserPolicy
        
        # Invalidate all users with this policy
        user_ids = UserPolicy.objects.filter(
            policy_id=instance.policy_id, 
            is_active=True
        ).values_list('user_id', flat=True)
        
        for user_id in user_ids:
            PermissionCache.invalidate_user_all(user_id)
            
    except ImportError:
        pass


@receiver(post_save, sender='abac.Policy')
def invalidate_policy_cache(sender, instance, **kwargs):
    """Invalidate cache when policy is updated"""
    try:
        from apps.core.permission_cache import PermissionCache
        from apps.abac.models import UserPolicy
        
        # Invalidate all users with this policy
        user_ids = UserPolicy.objects.filter(
            policy_id=instance.id, 
            is_active=True
        ).values_list('user_id', flat=True)
        
        for user_id in user_ids:
            PermissionCache.invalidate_user_all(user_id)
            
    except ImportError:
        pass


@receiver(post_save, sender='abac.GroupPolicy')
@receiver(post_delete, sender='abac.GroupPolicy')
def invalidate_group_policy_cache(sender, instance, **kwargs):
    """Invalidate cache when group policies change"""
    try:
        from apps.core.permission_cache import PermissionCache
        # Invalidate all caches as group membership is dynamic
        PermissionCache.clear_all()
    except ImportError:
        pass


# ============================================================================
# ROLE PERMISSION CHANGES
# ============================================================================

@receiver(post_save, sender='abac.Role')
def invalidate_on_role_permission_change(sender, instance, **kwargs):
    """
    When a role's permissions change, invalidate sessions for all users
    with that role to ensure they get the updated permissions.
    """
    try:
        from apps.abac.models import RoleAssignment
        from apps.authentication.models import User
        
        # Get all users with this role
        user_ids = RoleAssignment.objects.filter(
            role=instance,
            is_active=True
        ).values_list('user_id', flat=True)
        
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                _invalidate_user_sessions(
                    user=user,
                    reason=f"Role permissions updated: {instance.name}"
                )
            except User.DoesNotExist:
                pass
                
    except Exception as e:
        logger.error(f"Error invalidating sessions on role change: {e}")
