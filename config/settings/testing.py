"""
Django Settings - Testing Configuration
"""

from .base import *

DEBUG = False
TESTING = True

# Use faster password hasher
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Database - Standard PostgreSQL for organization-based isolation
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='ps_intellihr'),
        'USER': config('DB_USER', default='hrms_admin'),
        'PASSWORD': config('DB_PASSWORD', default='password'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'TEST': {
            'NAME': 'test_ps_intellihr_temp',
            'CHARSET': 'UTF8',
        }
    }
}

# The test runner will handle creating the public schema and migrations
# We just need to make sure the database engine is correct.
MIGRATION_MODULES = {}

# Testing throttle profile:
# - Default: disabled for deterministic OpenAPI suites
# - Optional: can be enabled with very high limits for throttle testing
ENABLE_TEST_THROTTLING = config("ENABLE_TEST_THROTTLING", default=False, cast=bool)
TEST_THROTTLE_RATES = {
    "anon": "20000/hour",
    "user": "200000/hour",
    "burst": "5000/minute",
    "sustained": "2000000/day",
    "organization": "500000/hour",
    "org_user": "200000/hour",
    "login": "300/minute",
    "password_reset": "500/hour",
    "two_factor": "1000/hour",
    "attendance_punch": "600/minute",
    "report_export": "500/hour",
    "api_key": "200000/hour",
}

if ENABLE_TEST_THROTTLING:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
        "apps.core.throttling.BurstRateThrottle",
        "apps.core.throttling.SustainedRateThrottle",
        "apps.core.throttling.OrganizationRateThrottle",
        "apps.core.throttling.OrganizationUserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ]
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = TEST_THROTTLE_RATES
else:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = TEST_THROTTLE_RATES

# Use sync Celery
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Fast deterministic in-process cache for tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "hrms-tests-cache",
    }
}

# Disable logging during tests
LOGGING = {}

# Email - In-memory backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
