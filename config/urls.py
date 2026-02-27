from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularRedocView, SpectacularSwaggerView

from apps.core.compat_views import DocumentCompatView
from apps.core.views_media import SecureMediaView


# ---------- Health / Readiness probes -----------------------------------------

def health_check(request):
    """Liveness probe — always returns 200 if the process is running."""
    return JsonResponse({"status": "ok"})


def readiness_check(request):
    """Readiness probe — checks database and Redis connectivity."""
    from django.db import connection
    from django.core.cache import cache
    checks = {"db": "ok", "cache": "ok"}
    status_code = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as exc:
        checks["db"] = str(exc)
        status_code = 503

    try:
        cache.set("_readiness_probe", "1", timeout=5)
        val = cache.get("_readiness_probe")
        if val != "1":
            checks["cache"] = "read-back failed"
            status_code = 503
    except Exception as exc:
        checks["cache"] = str(exc)
        status_code = 503

    overall = "ready" if status_code == 200 else "not_ready"
    return JsonResponse({"status": overall, **checks}, status=status_code)


def deep_health_check(request):
    """
    Deep health check for monitoring systems.
    Returns component statuses, migration state, and RLS status.
    """
    import time
    from django.db import connection
    from django.core.cache import cache

    start = time.monotonic()
    components = {}

    # Database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        components["database"] = {"status": "up", "engine": connection.vendor}
    except Exception as exc:
        components["database"] = {"status": "down", "error": str(exc)}

    # Cache/Redis
    try:
        cache.set("_health_deep", "ok", timeout=5)
        if cache.get("_health_deep") == "ok":
            components["cache"] = {"status": "up"}
        else:
            components["cache"] = {"status": "degraded"}
    except Exception as exc:
        components["cache"] = {"status": "down", "error": str(exc)}

    # Pending migrations
    try:
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command("showmigrations", "--plan", stdout=out, no_color=True)
        pending = [line for line in out.getvalue().splitlines() if line.strip().startswith("[ ]")]
        components["migrations"] = {
            "status": "ok" if not pending else "pending",
            "pending_count": len(pending),
        }
    except Exception:
        components["migrations"] = {"status": "unknown"}

    # RLS (PostgreSQL only)
    if connection.vendor == "postgresql":
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT count(*) FROM pg_class
                    WHERE relrowsecurity = true
                      AND relnamespace = 'public'::regnamespace
                """)
                rls_count = cursor.fetchone()[0]
            components["rls"] = {"status": "enabled", "protected_tables": rls_count}
        except Exception:
            components["rls"] = {"status": "unknown"}

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    all_up = all(c.get("status") in ("up", "ok", "enabled") for c in components.values())

    return JsonResponse({
        "status": "healthy" if all_up else "degraded",
        "response_time_ms": elapsed_ms,
        "components": components,
    }, status=200 if all_up else 503)


urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),

    # Health probes (exempt from auth & subscription middleware)
    path("api/v1/health/", health_check, name="health-check"),
    path("api/v1/readiness/", readiness_check, name="readiness-check"),
    path("api/v1/health/deep/", deep_health_check, name="deep-health-check"),

    path("api/v1/auth/", include("apps.authentication.urls")),
    path("api/v1/employees/", include("apps.employees.urls")),
    path("api/v1/recruitment/", include("apps.recruitment.urls")),
    path("api/v1/attendance/", include("apps.attendance.urls")),
    path("api/v1/leave/", include("apps.leave.urls")),
    path("api/v1/payroll/", include("apps.payroll.urls")),
    path("api/v1/performance/", include("apps.performance.urls")),
    path("api/v1/workflows/", include("apps.workflows.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/ai/", include("apps.ai_services.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/compliance/", include("apps.compliance.urls")),
    path("api/v1/integrations/", include("apps.integrations.urls")),
    path("api/v1/billing/", include("apps.billing.urls")),
    path("api/admin/billing/", include("apps.billing.admin_urls")),
    path("api/v1/abac/", include("apps.abac.urls")),
    path("api/v1/core/", include("apps.core.urls")),
    path("api/v1/onboarding/", include("apps.onboarding.urls")),
    path("api/v1/expenses/", include("apps.expenses.urls")),
    path("api/v1/assets/", include("apps.assets.urls")),
    path("api/v1/chat/", include("apps.chat.urls")),
    path("api/v1/training/", include("apps.training.urls")),
    path("api/v1/documents/", DocumentCompatView.as_view()),
    path("api/v1/documents/<path:subpath>/", DocumentCompatView.as_view()),

    # Authenticated media serving
    path("api/media/<path:file_path>", SecureMediaView.as_view(), name="secure-media"),
]

if getattr(settings, "ENABLE_API_DOCS", False):
    urlpatterns += [
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url="/static/schema.json"),
            name="swagger-ui",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url="/static/schema.json"),
            name="redoc",
        ),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

