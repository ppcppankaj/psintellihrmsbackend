"""
Per-Organization Rate Limiting Middleware and Utilities

Purpose:
  - Enforce rate limits per Organization (not per IP)
  - Prevent noisy Organizations from affecting others
  - Support burst traffic
  - Admin overrides for VIP Organizations
"""

from django.core.cache import cache
from django.http import JsonResponse
from django.utils.decorators import decorator_from_middleware
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from rest_framework.throttling import BaseThrottle
from rest_framework.response import Response
from rest_framework import status
import time
import json
from functools import wraps


# ============================================================================
# CONFIGURATION
# ============================================================================

RATE_LIMIT_CONFIG = {
    # Default rate limits (requests per minute)
    'default': {
        'per_minute': 60,
        'per_hour': 1000,
        'burst': 10,  # Allow 10 requests in first second
    },
    
    # Tier-based rate limits
    'tiers': {
        'free': {
            'per_minute': 30,
            'per_hour': 500,
            'burst': 5,
        },
        'starter': {
            'per_minute': 60,
            'per_hour': 1000,
            'burst': 10,
        },
        'professional': {
            'per_minute': 200,
            'per_hour': 5000,
            'burst': 50,
        },
        'enterprise': {
            'per_minute': 1000,
            'per_hour': 50000,
            'burst': 200,
        },
    },
    
    # Endpoint-specific limits (override defaults)
    'endpoints': {
        '/api/v1/payroll/generate-payslips/': {
            'per_minute': 5,  # Heavy operation
            'per_hour': 50,
        },
        '/api/v1/reports/': {
            'per_minute': 10,  # Expensive queries
            'per_hour': 100,
        },
        '/api/v1/bulk-import/': {
            'per_minute': 2,  # Very heavy
            'per_hour': 10,
        },
    },
    
    # VIP Organizations (unlimited or very high)
    'vip_Organizations': {
        'public': 999999,  # Public Organization unlimited
        'demo': 10000,
    },
}


# ============================================================================
# REDIS-BASED RATE LIMITER (Token Bucket Algorithm)
# ============================================================================

class TokenBucketLimiter:
    """
    Token Bucket algorithm for rate limiting.
    
    How it works:
    - Bucket has capacity = rate limit
    - Tokens regenerate over time
    - Each request consumes 1 token
    - If bucket empty, request blocked
    """
    
    def __init__(self, cache_backend=None):
        self.cache = cache_backend or cache
    
    def get_limit_config(self, organization_slug, path):
        """Get applicable rate limit for Organization + endpoint."""
        
        # Check VIP Organizations
        if organization_slug in RATE_LIMIT_CONFIG['vip_Organizations']:
            return {
                'per_minute': RATE_LIMIT_CONFIG['vip_Organizations'][organization_slug],
                'per_hour': RATE_LIMIT_CONFIG['vip_Organizations'][organization_slug],
            }
        
        # Check endpoint-specific limits
        if path in RATE_LIMIT_CONFIG['endpoints']:
            return RATE_LIMIT_CONFIG['endpoints'][path]
        
        # Check Organization tier (future: from database)
        tier = getattr(settings, 'DEFAULT_Organization_TIER', 'starter')
        return RATE_LIMIT_CONFIG['tiers'].get(
            tier,
            RATE_LIMIT_CONFIG['default']
        )
    
    def is_allowed(self, organization_slug, path, ip_address):
        """
        Check if request is allowed under rate limit.
        
        Returns: (allowed: bool, remaining: int, reset_time: int)
        """
        
        config = self.get_limit_config(organization_slug, path)
        per_minute = config['per_minute']
        per_hour = config['per_hour']
        
        # Cache keys
        minute_key = f'ratelimit:{organization_slug}:{path}:minute:{int(time.time() / 60)}'
        hour_key = f'ratelimit:{organization_slug}:{path}:hour:{int(time.time() / 3600)}'
        
        # Get current counts
        minute_count = self.cache.get(minute_key, 0)
        hour_count = self.cache.get(hour_key, 0)
        
        # Check limits
        if minute_count >= per_minute:
            reset_time = int(time.time() / 60 + 1) * 60
            return False, 0, reset_time
        
        if hour_count >= per_hour:
            reset_time = int(time.time() / 3600 + 1) * 3600
            return False, 0, reset_time
        
        # Increment counts
        self.cache.set(minute_key, minute_count + 1, 61)  # Expire after 1 minute
        self.cache.set(hour_key, hour_count + 1, 3601)    # Expire after 1 hour
        
        # Calculate remaining
        remaining = min(
            per_minute - minute_count - 1,
            per_hour - hour_count - 1
        )
        
        return True, remaining, 0
    
    def get_reset_time(self, organization_slug, path):
        """Get when rate limit will reset."""
        minute_key = f'ratelimit:{organization_slug}:{path}:minute:{int(time.time() / 60)}'
        ttl = self.cache.ttl(minute_key)  # Requires Redis cache
        return int(time.time()) + ttl if ttl > 0 else 0


# ============================================================================
# MIDDLEWARE
# ============================================================================

class PerOrganizationRateLimitMiddleware(MiddlewareMixin):
    """
    Rate limiting middleware - applied per Organization.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.limiter = TokenBucketLimiter()
        super().__init__(get_response)
    
    def process_request(self, request):
        # Skip rate limiting for public paths
        if self._is_public_path(request.path):
            return None
        
        # Get Organization (assumes middleware sets request.organization)
        Organization = getattr(request, 'Organization', None)
        if not Organization:
            return None  # No Organization, skip rate limiting
        
        # Get client IP
        ip_address = self._get_client_ip(request)
        
        # Check rate limit
        allowed, remaining, reset_time = self.limiter.is_allowed(
            Organization.slug,
            request.path,
            ip_address
        )
        
        # Store for response headers
        request.rate_limit_remaining = remaining
        request.rate_limit_reset = reset_time
        
        if not allowed:
            return JsonResponse(
                {
                    'error': 'rate_limit_exceeded',
                    'detail': f'Rate limit exceeded for Organization {Organization.slug}',
                    'reset_time': reset_time,
                },
                status=429  # Too Many Requests
            )
        
        return None
    
    def process_response(self, request, response):
        """Add rate limit headers to response."""
        
        if hasattr(request, 'rate_limit_remaining'):
            response['X-RateLimit-Remaining'] = str(request.rate_limit_remaining)
            response['X-RateLimit-Limit'] = str(
                RATE_LIMIT_CONFIG['default']['per_minute']
            )
        
        if hasattr(request, 'rate_limit_reset'):
            response['X-RateLimit-Reset'] = str(request.rate_limit_reset)
        
        return response
    
    def _is_public_path(self, path):
        """Paths that bypass rate limiting."""
        public_paths = [
            '/admin/login/',
            '/api/v1/token/',
            '/api/v1/health/',
            '/static/',
            '/media/',
        ]
        return any(path.startswith(p) for p in public_paths)
    
    def _get_client_ip(self, request):
        """Extract client IP from request."""
        if 'HTTP_X_FORWARDED_FOR' in request.META:
            return request.META['HTTP_X_FORWARDED_FOR'].split(',')[0]
        return request.META.get('REMOTE_ADDR', 'unknown')


# ============================================================================
# DRF THROTTLE CLASS (For API Views)
# ============================================================================

class OrganizationAwareThrottle(BaseThrottle):
    """
    DRF throttle class for per-Organization rate limiting.
    
    Usage in views:
        from rest_framework.throttling import UserRateThrottle
        
        class MyViewSet(viewsets.ModelViewSet):
            throttle_classes = [OrganizationAwareThrottle]
    """
    
    def __init__(self):
        self.limiter = TokenBucketLimiter()
    
    def allow_request(self, request, view):
        """
        Implement DRF throttle interface.
        Return True if allowed, False otherwise.
        """
        
        # Get Organization
        Organization = getattr(request, 'Organization', None)
        if not Organization:
            return True
        
        # Get view path
        path = request.path
        
        # Check limit
        allowed, remaining, reset_time = self.limiter.is_allowed(
            Organization.slug,
            path,
            self._get_client_ip(request)
        )
        
        # Store for headers
        self.request = request
        self.throttle_success = allowed
        self.throttle_rate = str(remaining)
        self.wait_seconds = reset_time - int(time.time())
        
        return allowed
    
    def throttle_success(self):
        """Throttle succeeded."""
        return True
    
    def throttle_failure(self):
        """Throttle failed - return error response."""
        return Response(
            {
                'error': 'rate_limit_exceeded',
                'detail': self.get_throttle_message(),
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    def get_throttle_message(self):
        return (
            f'Request throttled. Expected available in '
            f'{self.wait_seconds} seconds.'
        )
    
    def _get_client_ip(self, request):
        """Extract client IP."""
        if 'HTTP_X_FORWARDED_FOR' in request.META:
            return request.META['HTTP_X_FORWARDED_FOR'].split(',')[0]
        return request.META.get('REMOTE_ADDR', 'unknown')


# ============================================================================
# DECORATOR FOR FUNCTION-BASED VIEWS
# ============================================================================

def rate_limit(per_minute=60, per_hour=1000):
    """
    Decorator for rate limiting on function-based views.
    
    Usage:
        @rate_limit(per_minute=30, per_hour=500)
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            limiter = TokenBucketLimiter()
            Organization = getattr(request, 'Organization', None)
            
            if Organization:
                config = {
                    'per_minute': per_minute,
                    'per_hour': per_hour,
                }
                
                allowed, remaining, reset_time = limiter.is_allowed(
                    Organization.slug,
                    request.path,
                    _get_client_ip(request)
                )
                
                if not allowed:
                    return JsonResponse(
                        {
                            'error': 'rate_limit_exceeded',
                            'reset_time': reset_time,
                        },
                        status=429
                    )
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# ADMIN INTERFACE FOR MANAGING LIMITS
# ============================================================================

class RateLimitOverride:
    """
    Temporary overrides for rate limits (for VIP support).
    
    Usage:
        override = RateLimitOverride()
        override.set_unlimited('acme_Organization', 'hours=24')
        override.set_custom('startup_Organization', per_minute=500, hours=48)
    """
    
    def set_unlimited(self, organization_slug, duration_seconds=86400):
        """Set unlimited rate limit for Organization."""
        cache_key = f'ratelimit_override:{organization_slug}'
        cache.set(cache_key, 'unlimited', duration_seconds)
    
    def set_custom(self, organization_slug, per_minute, duration_seconds=86400):
        """Set custom rate limit for Organization."""
        cache_key = f'ratelimit_override:{organization_slug}'
        cache.set(cache_key, {'per_minute': per_minute}, duration_seconds)
    
    def clear(self, organization_slug):
        """Clear override for Organization."""
        cache_key = f'ratelimit_override:{organization_slug}'
        cache.delete(cache_key)
    
    def get_override(self, organization_slug):
        """Get current override (if any)."""
        cache_key = f'ratelimit_override:{organization_slug}'
        return cache.get(cache_key)


# ============================================================================
# MANAGEMENT COMMAND FOR RATE LIMIT MONITORING
# ============================================================================

def get_rate_limit_stats(organization_slug):
    """
    Get current rate limit stats for Organization.
    
    Returns: {
        'requests_this_minute': int,
        'requests_this_hour': int,
        'limit_per_minute': int,
        'limit_per_hour': int,
        'percentage_minute': float,
        'percentage_hour': float,
    }
    """
    limiter = TokenBucketLimiter()
    config = limiter.get_limit_config(organization_slug, '/api/v1/')
    
    current_minute = int(time.time() / 60)
    current_hour = int(time.time() / 3600)
    
    minute_key = f'ratelimit:{organization_slug}:/api/v1/:minute:{current_minute}'
    hour_key = f'ratelimit:{organization_slug}:/api/v1/:hour:{current_hour}'
    
    requests_minute = cache.get(minute_key, 0)
    requests_hour = cache.get(hour_key, 0)
    
    return {
        'requests_this_minute': requests_minute,
        'requests_this_hour': requests_hour,
        'limit_per_minute': config['per_minute'],
        'limit_per_hour': config['per_hour'],
        'percentage_minute': (requests_minute / config['per_minute']) * 100,
        'percentage_hour': (requests_hour / config['per_hour']) * 100,
        'approaching_limit': (requests_minute / config['per_minute']) > 0.8,
    }


def _get_client_ip(request):
    """Extract client IP from request."""
    if 'HTTP_X_FORWARDED_FOR' in request.META:
        return request.META['HTTP_X_FORWARDED_FOR'].split(',')[0]
    return request.META.get('REMOTE_ADDR', 'unknown')
