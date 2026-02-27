"""
Django Settings — Production Configuration
Enterprise HRMS SaaS Platform
"""

from .base import *  # noqa: F401,F403
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

if not REDIS_CACHE_URL:
    raise ImproperlyConfigured(
        "REDIS_CACHE_URL is required in production for distributed throttling."
    )

# ── RLS enforcement: require RLS when using PostgreSQL in production ──
_db_engine = DATABASES.get("default", {}).get("ENGINE", "")
if "postgresql" in _db_engine:
    _rls_enabled = config("ENABLE_POSTGRESQL_RLS", default=False, cast=bool)
    if not _rls_enabled:
        raise ImproperlyConfigured(
            "ENABLE_POSTGRESQL_RLS must be True in production with PostgreSQL. "
            "Row-Level Security is required for tenant data isolation."
        )

# ── Production safety assertions ──
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must not contain '*' in production."
    )

if not config("RAZORPAY_WEBHOOK_SECRET", default=""):
    import warnings
    warnings.warn(
        "RAZORPAY_WEBHOOK_SECRET is not set. Razorpay webhooks will be rejected.",
        stacklevel=1,
    )

# ============================================================================
# SECURITY HARDENING
# ============================================================================

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
CSRF_USE_SESSIONS = False

SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default=f"https://{BASE_DOMAIN},https://*.{BASE_DOMAIN}",
    cast=Csv(),
)
CSRF_COOKIE_DOMAIN = config("CSRF_COOKIE_DOMAIN", default=f".{BASE_DOMAIN}")
SESSION_COOKIE_DOMAIN = config("SESSION_COOKIE_DOMAIN", default=f".{BASE_DOMAIN}")

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

ENABLE_API_DOCS = config("ENABLE_API_DOCS", default=False, cast=bool)

# Enable nginx X-Accel-Redirect for authenticated media serving
USE_NGINX_ACCEL_REDIRECT = True

# ============================================================================
# CORS (production – restrict to known origins)
# ============================================================================

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default=f"https://{BASE_DOMAIN}",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ============================================================================
# EMAIL (SMTP – production)
# ============================================================================

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="PS IntelliHR <noreply@yourdomain.com>"
)

# ============================================================================
# CELERY — production overrides
# ============================================================================

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL or "redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL or "redis://redis:6379/0")
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# ============================================================================
# REST FRAMEWORK – THROTTLING
# ============================================================================

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
    "anon": config("THROTTLE_ANON_RATE", default="120/hour"),
    "user": config("THROTTLE_USER_RATE", default="3000/hour"),
    "burst": config("THROTTLE_BURST_RATE", default="180/minute"),
    "sustained": config("THROTTLE_SUSTAINED_RATE", default="50000/day"),
    "organization": config("THROTTLE_ORGANIZATION_RATE", default="200000/hour"),
    "org_user": config("THROTTLE_ORG_USER_RATE", default="30000/hour"),
    "login": config("THROTTLE_LOGIN_RATE", default="10/minute"),
    "password_reset": config("THROTTLE_PASSWORD_RESET_RATE", default="8/hour"),
    "two_factor": config("THROTTLE_TWO_FACTOR_RATE", default="30/hour"),
    "attendance_punch": config("THROTTLE_ATTENDANCE_PUNCH_RATE", default="60/minute"),
    "report_export": config("THROTTLE_REPORT_EXPORT_RATE", default="30/hour"),
    "api_key": config("THROTTLE_API_KEY_RATE", default="10000/hour"),
}

# ============================================================================
# LOGGING (JSON structured – stdout for Docker)
# ============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": "apps.core.logging.CorrelationIdFilter",
        }
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "gunicorn": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.core.exceptions": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "security.audit": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ============================================================================
# SENTRY
# ============================================================================

import sentry_sdk  # noqa: E402
from sentry_sdk.integrations.django import DjangoIntegration  # noqa: E402
from sentry_sdk.integrations.celery import CeleryIntegration  # noqa: E402
from sentry_sdk.integrations.redis import RedisIntegration  # noqa: E402

SENTRY_DSN = config("SENTRY_DSN", default="")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.1, cast=float),
        send_default_pii=False,
        environment=ENVIRONMENT,
    )
