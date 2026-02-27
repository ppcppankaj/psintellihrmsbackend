"""
Django Settings - Development Configuration
"""

from .base import *

DEBUG = True

# ALLOWED_HOSTS is set in base.py based on DEBUG flag (accepts all hosts in dev)

# Debug toolbar (Disabled per user request)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
# INTERNAL_IPS = ['127.0.0.1']

# Database logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Development throttle profile: permissive but still active.
DEV_DISABLE_THROTTLING = config("DEV_DISABLE_THROTTLING", default=False, cast=bool)

if DEV_DISABLE_THROTTLING:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}
else:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
        "apps.core.throttling.BurstRateThrottle",
        "apps.core.throttling.SustainedRateThrottle",
        "apps.core.throttling.OrganizationRateThrottle",
        "apps.core.throttling.OrganizationUserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ]
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
        "anon": "5000/hour",
        "user": "30000/hour",
        "burst": "600/minute",
        "sustained": "250000/day",
        "organization": "100000/hour",
        "org_user": "50000/hour",
        "login": "30/minute",
        "password_reset": "20/hour",
        "two_factor": "120/hour",
        "attendance_punch": "120/minute",
        "report_export": "120/hour",
        "api_key": "20000/hour",
    }

# Email - Console backend
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# CORS - Allow all in development
 # CORS_ALLOW_ALL_ORIGINS = True  # Disabled for security
