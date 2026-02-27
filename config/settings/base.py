"""
Django Settings - Base Configuration
Enterprise HRMS SaaS Platform
"""

import os
import sys
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured
from celery.schedules import crontab

# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# SECURITY
# =============================================================================

DEBUG = config("DEBUG", default=True, cast=bool)

SECRET_KEY = config(
    "SECRET_KEY",
    default="django-insecure-development-key-change-in-production",
)

FIELD_ENCRYPTION_KEY = config(
    "FIELD_ENCRYPTION_KEY",
    default="JKLjPxZvMnBqWrStUvWxYzAbCdEfGhIjKlMnOpQrStUv=",
)

# Block unsafe production deploys
if not DEBUG and SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured("SECRET_KEY must be set in production")

if not DEBUG and FIELD_ENCRYPTION_KEY == "JKLjPxZvMnBqWrStUvWxYzAbCdEfGhIjKlMnOpQrStUv=":
    raise ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY must be changed from default in production"
    )

# =============================================================================
# ENVIRONMENT
# =============================================================================

ENVIRONMENT = config("ENVIRONMENT", default="development")

IS_MANAGEMENT_COMMAND = any(
    cmd in sys.argv
    for cmd in [
        "makemigrations",
        "migrate",
        "shell",
        "loaddata",
        "collectstatic",
        "createsuperuser",
        "flush",
        "dumpdata",
        "test",
    ]
)

REQUIRE_ORGANIZATION_CONTEXT = (
    False if IS_MANAGEMENT_COMMAND
    else config("REQUIRE_ORGANIZATION_CONTEXT", default=True, cast=bool)
)

# =============================================================================
# HOSTS
# =============================================================================

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = config(
        "ALLOWED_HOSTS",
        default="localhost,127.0.0.1",
        cast=Csv(),
    )

BASE_DOMAIN = config("BASE_DOMAIN", default="localhost")

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# =============================================================================
# APPLICATIONS
# =============================================================================

INSTALLED_APPS = [
    "daphne",

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Auth
    "apps.authentication",

    # Domain apps
    "apps.core",
    "apps.billing",
    "apps.abac",
    "apps.employees",
    "apps.recruitment",
    "apps.attendance",
    "apps.leave",
    "apps.payroll",
    "apps.performance",
    "apps.workflows",
    "apps.notifications",
    "apps.ai_services",
    "apps.reports",
    "apps.compliance",
    "apps.integrations",
    "apps.training",
    "apps.onboarding",
    "apps.expenses",
    "apps.assets",
    "apps.chat",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_results",
    "django_celery_beat",
    "channels",
]

# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    # Security (MUST be first)
    "django.middleware.security.SecurityMiddleware",

    # Static files
    "whitenoise.middleware.WhiteNoiseMiddleware",

    # CORS (must be early)
    "corsheaders.middleware.CorsMiddleware",

    # Sessions MUST come before CSRF
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",

    # CSRF must be BEFORE AuthenticationMiddleware
    "django.middleware.csrf.CsrfViewMiddleware",

    # Auth
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # Domain-based tenant mapping
    "apps.core.middleware_domain.DomainTenantMiddleware",
    "apps.authentication.middleware.JWTDomainEnforcementMiddleware",

    # ---- Your custom middlewares (safe AFTER auth) ----
    "apps.core.middleware.CorrelationIdMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.middleware.MetricsMiddleware",
    "apps.core.middleware.AuditMiddleware",
    "apps.core.middleware.InputSanitizationMiddleware",

    # Tenant / org context
    "apps.core.middleware_organization.OrganizationMiddleware",
    "apps.core.middleware_rls.RLSContextMiddleware",
    "apps.core.middleware.BranchContextMiddleware",
    "apps.billing.middleware.SubscriptionMiddleware",

    # Messages + security headers last
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]




# =============================================================================
# URL / ASGI / WSGI
# =============================================================================

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# =============================================================================
# TEMPLATES
# =============================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# =============================================================================
# DATABASE (SMART & EC2 SAFE)
# =============================================================================

DATABASE_URL = config("DATABASE_URL", default="")

if DATABASE_URL.startswith("sqlite"):
    # ✅ SQLite (EC2 / Free tier / Local)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

else:
    # ✅ PostgreSQL (Only when explicitly configured)
    POSTGRES_PASSWORD = config("POSTGRES_PASSWORD", default=None)

    if not POSTGRES_PASSWORD:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "PostgreSQL selected but POSTGRES_PASSWORD is missing"
        )

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB"),
            "USER": config("POSTGRES_USER"),
            "PASSWORD": POSTGRES_PASSWORD,
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": 60,
            "ATOMIC_REQUESTS": True,  # Required for SET LOCAL RLS context
        }
    }



# =============================================================================
# REDIS / CHANNELS (OPTIONAL)
# =============================================================================

REDIS_URL = config("REDIS_URL", default=None)
REDIS_CACHE_URL = config("REDIS_CACHE_URL", default=REDIS_URL)

if REDIS_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "KEY_PREFIX": f"hrms:{ENVIRONMENT}",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"hrms-{ENVIRONMENT}-cache",
        }
    }

CHANNEL_LAYER_IN_MEMORY = config("CHANNEL_LAYER_IN_MEMORY", default=False, cast=bool)
CHANNEL_LAYER_URL = config("CHANNEL_LAYER_URL", default=None)
CHANNEL_LAYER_HOST = config("CHANNEL_LAYER_HOST", default="127.0.0.1")
CHANNEL_LAYER_PORT = config("CHANNEL_LAYER_PORT", default=6379, cast=int)
CHANNEL_LAYER_DB = config("CHANNEL_LAYER_DB", default=3, cast=int)

if CHANNEL_LAYER_IN_MEMORY:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
else:
    if CHANNEL_LAYER_URL:
        channel_hosts = [CHANNEL_LAYER_URL]
    elif REDIS_URL:
        channel_hosts = [f"{REDIS_URL}/{CHANNEL_LAYER_DB}"]
    else:
        channel_hosts = [(CHANNEL_LAYER_HOST, CHANNEL_LAYER_PORT)]

    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": channel_hosts},
        }
    }

# =============================================================================
# AUTH
# =============================================================================

AUTH_USER_MODEL = "authentication.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =============================================================================
# I18N
# =============================================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC / MEDIA
# =============================================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# DRF
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.authentication.authentication.OrganizationAwareJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated"
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "apps.core.renderers.StandardJSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.core.rbac_hardening.OrganizationRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "org": "1000/hour",
        "login": "5/minute",
        "burst": "20/minute",
        "password_reset": "3/hour",
        "two_factor": "5/minute",
        "anon": "30/minute",
    },
    "DEFAULT_THROTTLE_CACHE": "default",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

# =============================================================================
# JWT
# =============================================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}


# =============================================================================
# CELERY
# =============================================================================

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600          # hard kill after 10 min
CELERY_TASK_SOFT_TIME_LIMIT = 540     # soft warning at 9 min

CELERY_BEAT_SCHEDULE = {
    # -- Billing --
    "billing.subscription.expiry": {
        "task": "billing.tasks.subscription_expiry_task",
        "schedule": crontab(hour=0, minute=0),     # midnight daily
        "options": {"queue": "billing"},
    },
    # -- Payroll --
    "payroll.generate": {
        "task": "apps.payroll.tasks.generate_payroll",
        "schedule": crontab(hour=1, minute=0, day_of_month=1),   # 1st of month
        "options": {"queue": "payroll"},
    },
}

# =============================================================================
# EMAIL
# =============================================================================

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

DEFAULT_FROM_EMAIL = "HRMS <noreply@pankaj.im>"
EMAIL_PORT = config("EMAIL_PORT", default=465, cast=int)
EMAIL_USE_SSL = True

# =============================================================================
# AI
# =============================================================================

OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
AI_MODEL_PATH = BASE_DIR / "ai_models"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
ENABLE_API_DOCS = config("ENABLE_API_DOCS", default=DEBUG, cast=bool)

SPECTACULAR_SETTINGS = {
    "TITLE": "PS IntelliHR API",
    "DESCRIPTION": "Enterprise HRMS Platform",
    "VERSION": "1.0.0",

    # Core
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",

    # Silence known DRF noise
    "COMPONENT_SPLIT_REQUEST": True,
    "DISABLE_ERRORS_AND_WARNINGS": False,

    # 🔥 IMPORTANT
    "ENUM_NAME_OVERRIDES": {
        # end_day_type appears in multiple models
        "EndDayType": "EndDayTypeEnum",
    },
    "SCHEMA_COERCE_PATH_PK_SUFFIX": True,
    "SCHEMA_COERCE_METHOD_NAMES": True,
    "DISABLE_ERRORS_AND_WARNINGS": False,
"ENUM_NAME_OVERRIDES": {
        "StatusEnum": [
            "apps.billing.models.Subscription.status",
            "apps.billing.models.Invoice.paid_status",
            "apps.payroll.models.PayrollRun.status",
            "apps.leave.models.LeaveRequest.status",
        ],
        "StartDayTypeEnum": [
            "apps.leave.models.LeavePolicy.start_day_type",
        ],
        "EndDayTypeEnum": [
            "apps.leave.models.LeavePolicy.end_day_type",
        ],
    },
}

# =============================================================================
# Payments / Gateways
# =============================================================================

RAZORPAY_KEY_ID = config("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = config("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_CURRENCY = config("RAZORPAY_CURRENCY", default="INR")
RAZORPAY_WEBHOOK_SECRET = config("RAZORPAY_WEBHOOK_SECRET", default="")

# =============================================================================
# Billing Company Profile
# =============================================================================

BILLING_COMPANY_NAME = config("BILLING_COMPANY_NAME", default="PS IntelliHR")
BILLING_COMPANY_ADDRESS = config("BILLING_COMPANY_ADDRESS", default="")
BILLING_COMPANY_GSTIN = config("BILLING_COMPANY_GSTIN", default="")
BILLING_COMPANY_LOGO_URL = config("BILLING_COMPANY_LOGO_URL", default="")
BILLING_PORTAL_BASE_URL = config(
    "BILLING_PORTAL_BASE_URL",
    default=f"https://{BASE_DOMAIN}",
)
