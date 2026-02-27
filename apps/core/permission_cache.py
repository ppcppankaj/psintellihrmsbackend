"""
Permission Cache - Redis-based caching for RBAC performance
"""

from django.core.cache import cache
from django.conf import settings
import hashlib
import json


class PermissionCache:
    """
    Redis-based permission caching for performance at scale.
    Caches: role permissions, field masks, menu access.
    """
    
    CACHE_TTL = getattr(settings, 'PERMISSION_CACHE_TTL', 300)  # 5 minutes
    CACHE_PREFIX = 'perm:'
    
    @classmethod
    def _make_key(cls, *parts):
        """Generate cache key"""
        key = ':'.join(str(p) for p in parts)
        return f"{cls.CACHE_PREFIX}{key}"
    
    # =========================================================================
    # USER PERMISSIONS
    # =========================================================================
    
    @classmethod
    def get_user_permissions(cls, user_id):
        """Get cached permissions for a user"""
        key = cls._make_key('user', user_id, 'permissions')
        return cache.get(key)
    
    @classmethod
    def set_user_permissions(cls, user_id, permissions):
        """Cache user permissions"""
        key = cls._make_key('user', user_id, 'permissions')
        cache.set(key, permissions, cls.CACHE_TTL)
    
    @classmethod
    def invalidate_user_permissions(cls, user_id):
        """Invalidate user permissions cache"""
        key = cls._make_key('user', user_id, 'permissions')
        cache.delete(key)
    
    # =========================================================================
    # USER ROLES
    # =========================================================================
    
    @classmethod
    def get_user_roles(cls, user_id):
        """Get cached roles for a user"""
        key = cls._make_key('user', user_id, 'roles')
        return cache.get(key)
    
    @classmethod
    def set_user_roles(cls, user_id, roles):
        """Cache user roles"""
        key = cls._make_key('user', user_id, 'roles')
        cache.set(key, roles, cls.CACHE_TTL)
    
    @classmethod
    def invalidate_user_roles(cls, user_id):
        """Invalidate user roles cache"""
        key = cls._make_key('user', user_id, 'roles')
        cache.delete(key)
    
    # =========================================================================
    # ROLE PERMISSIONS
    # =========================================================================
    
    @classmethod
    def get_role_permissions(cls, role_id):
        """Get cached permissions for a role"""
        key = cls._make_key('role', role_id, 'permissions')
        return cache.get(key)
    
    @classmethod
    def set_role_permissions(cls, role_id, permissions):
        """Cache role permissions"""
        key = cls._make_key('role', role_id, 'permissions')
        cache.set(key, permissions, cls.CACHE_TTL)
    
    @classmethod
    def invalidate_role_permissions(cls, role_id):
        """Invalidate role permissions cache"""
        key = cls._make_key('role', role_id, 'permissions')
        cache.delete(key)
    
    # =========================================================================
    # FIELD MASKS
    # =========================================================================
    
    @classmethod
    def get_field_masks(cls, user_id, model_name):
        """Get cached field masks for a user and model"""
        key = cls._make_key('user', user_id, 'mask', model_name)
        return cache.get(key)
    
    @classmethod
    def set_field_masks(cls, user_id, model_name, masks):
        """Cache field masks"""
        key = cls._make_key('user', user_id, 'mask', model_name)
        cache.set(key, masks, cls.CACHE_TTL)
    
    # =========================================================================
    # MENU ACCESS
    # =========================================================================
    
    @classmethod
    def get_menu_access(cls, user_id):
        """Get cached menu access for a user"""
        key = cls._make_key('user', user_id, 'menu')
        return cache.get(key)
    
    @classmethod
    def set_menu_access(cls, user_id, menu_items):
        """Cache menu access"""
        key = cls._make_key('user', user_id, 'menu')
        cache.set(key, menu_items, cls.CACHE_TTL)
    
    @classmethod
    def invalidate_menu_access(cls, user_id):
        """Invalidate menu access cache"""
        key = cls._make_key('user', user_id, 'menu')
        cache.delete(key)
    
    # =========================================================================
    # BULK INVALIDATION
    # =========================================================================
    
    @classmethod
    def invalidate_user_all(cls, user_id):
        """Invalidate all caches for a user"""
        cls.invalidate_user_permissions(user_id)
        cls.invalidate_user_roles(user_id)
        cls.invalidate_menu_access(user_id)
    
    @classmethod
    def invalidate_role_all(cls, role_id):
        """Invalidate all caches for a role (affects all users with this role)"""
        cls.invalidate_role_permissions(role_id)
        # Note: Should trigger invalidation for all users with this role
        # This is handled by role update signals


def cached_permission_check(user, permission_code):
    """
    Check permission with caching.
    First checks cache, then falls back to database.
    """
    if user.is_superuser:
        return True
    
    # Try cache first
    cached = PermissionCache.get_user_permissions(user.id)
    if cached is not None:
        return permission_code in cached
    
    # Fall back to database and cache result
    from apps.authentication.models import User
    permissions = user.get_all_permissions()
    PermissionCache.set_user_permissions(user.id, permissions)
    
    return permission_code in permissions


def cached_role_check(user, role_code):
    """
    Check role with caching.
    """
    if user.is_superuser:
        return True
    
    # Try cache first
    cached = PermissionCache.get_user_roles(user.id)
    if cached is not None:
        return role_code in cached
    
    # Fall back to database and cache result
    roles = user.get_role_codes()
    PermissionCache.set_user_roles(user.id, roles)
    
    return role_code in roles


def get_cached_menu_items(user):
    """
    Get menu items based on user permissions with caching.
    """
    if user.is_superuser:
        return get_all_menu_items()
    
    # Try cache first
    cached = PermissionCache.get_menu_access(user.id)
    if cached is not None:
        return cached
    
    # Build menu based on permissions
    menu_items = build_menu_for_user(user)
    PermissionCache.set_menu_access(user.id, menu_items)
    
    return menu_items


def get_all_menu_items():
    """Return all menu items for superusers"""
    return [
        {'id': 'dashboard', 'label': 'Dashboard', 'icon': 'dashboard', 'path': '/dashboard'},
        {'id': 'employees', 'label': 'Employees', 'icon': 'people', 'path': '/employees'},
        {'id': 'attendance', 'label': 'Attendance', 'icon': 'schedule', 'path': '/attendance'},
        {'id': 'leave', 'label': 'Leave', 'icon': 'event_busy', 'path': '/leave'},
        {'id': 'payroll', 'label': 'Payroll', 'icon': 'payments', 'path': '/payroll'},
        {'id': 'performance', 'label': 'Performance', 'icon': 'trending_up', 'path': '/performance'},
        {'id': 'recruitment', 'label': 'Recruitment', 'icon': 'work', 'path': '/recruitment'},
        {'id': 'reports', 'label': 'Reports', 'icon': 'assessment', 'path': '/reports'},
        {'id': 'settings', 'label': 'Settings', 'icon': 'settings', 'path': '/settings'},
    ]


def build_menu_for_user(user):
    """Build menu items based on user permissions"""
    all_items = get_all_menu_items()
    
    # Permission to menu mapping
    menu_permissions = {
        'dashboard': [],  # Always visible
        'employees': ['employees.view'],
        'attendance': ['attendance.view'],
        'leave': ['leave.view'],
        'payroll': ['payroll.view'],
        'performance': ['performance.view'],
        'recruitment': ['recruitment.view_jobs'],
        'reports': ['reports.view'],
        'settings': ['settings.view'],
    }
    
    # Get user permissions
    user_permissions = set(user.get_all_permissions())
    
    # Filter menu items
    visible_items = []
    for item in all_items:
        required = menu_permissions.get(item['id'], [])
        if not required or any(p in user_permissions for p in required):
            visible_items.append(item)
    
    return visible_items
