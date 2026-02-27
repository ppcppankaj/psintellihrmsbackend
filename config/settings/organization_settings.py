"""
Settings for Organization-Based Multi-Tenancy
Add these to your base.py and production.py settings files
"""

from decouple import config, Csv

# =============================================================================
# ORGANIZATION-BASED MULTI-TENANCY SETTINGS
# =============================================================================

# Environment (development, staging, production)
ENVIRONMENT = config('ENVIRONMENT', default='development')

# Enable PostgreSQL Row-Level Security for database-level isolation
# Recommended for production environments
ENABLE_POSTGRESQL_RLS = config('ENABLE_POSTGRESQL_RLS', default=False, cast=bool)

# Require organization context for all queries in production
# Prevents accidental data leakage by raising explicit errors
REQUIRE_ORGANIZATION_CONTEXT = (ENVIRONMENT == 'production')

# =============================================================================
# MIDDLEWARE CONFIGURATION
# =============================================================================

# Add OrganizationMiddleware after AuthenticationMiddleware
# MIDDLEWARE = [
#     'django.middleware.security.SecurityMiddleware',
#     'corsheaders.middleware.CorsMiddleware',
#     'django.contrib.sessions.middleware.SessionMiddleware',
#     'django.middleware.common.CommonMiddleware',
#     'django.middleware.csrf.CsrfViewMiddleware',
#     'django.contrib.auth.middleware.AuthenticationMiddleware',
#     'django.contrib.messages.middleware.MessageMiddleware',
#     'django.middleware.clickjacking.XFrameOptionsMiddleware',
#     
#     # NEW: Organization middleware (MUST be after AuthenticationMiddleware)
#     'apps.core.middleware_organization.OrganizationMiddleware',
# ]

# =============================================================================
# DATABASE CONFIGURATION (No Changes Needed)
# =============================================================================

# Single database configuration (no DATABASE_ROUTERS needed)
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': config('DB_NAME', default='hrms'),
#         'USER': config('DB_USER', default='postgres'),
#         'PASSWORD': config('DB_PASSWORD'),
#         'HOST': config('DB_HOST', default='localhost'),
#         'PORT': config('DB_PORT', default='5432', cast=int),
#         'ATOMIC_REQUESTS': True,
#         'CONN_MAX_AGE': 600,
#     }
# }

# =============================================================================
# SETTINGS TO REMOVE (From schema-based architecture)
# =============================================================================

# DELETE these if they exist:
# TENANT_MODEL = "tenants.Tenant"
# TENANT_DOMAIN_MODEL = "tenants.Domain"
# DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']
# SHARED_APPS = [...]
# TENANT_APPS = [...]

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Ensure logging captures organization context events
# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'formatters': {
#         'json': {
#             '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
#             'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
#         },
#     },
#     'handlers': {
#         'console': {
#             'class': 'logging.StreamHandler',
#             'formatter': 'json',
#         },
#     },
#     'loggers': {
#         'apps.core': {
#             'handlers': ['console'],
#             'level': 'INFO',
#             'propagate': False,
#         },
#     },
# }

# =============================================================================
# PRODUCTION SETTINGS OVERRIDES
# =============================================================================

# In production.py:
# ENVIRONMENT = 'production'
# ENABLE_POSTGRESQL_RLS = True
# REQUIRE_ORGANIZATION_CONTEXT = True
# DEBUG = False
