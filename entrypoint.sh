#!/bin/bash
set -e

echo "========================================="
echo "  PS IntelliHR — Container Entrypoint"
echo "========================================="
echo "  Mode : ${1:-web}"
echo "  Host : $(hostname)"
echo "========================================="

# ---------- Wait for database -------------------------------------------------
wait_for_db() {
    local host="${DB_HOST:-postgres}"
    local port="${DB_PORT:-5432}"
    local retries=30
    echo "[entrypoint] Waiting for PostgreSQL at ${host}:${port} ..."
    until nc -z "$host" "$port" 2>/dev/null; do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            echo "[entrypoint] ERROR: Postgres not reachable after 60 s"
            exit 1
        fi
        sleep 2
    done
    echo "[entrypoint] PostgreSQL is ready."
}

# ---------- Wait for Redis ----------------------------------------------------
wait_for_redis() {
    local url="${REDIS_URL:-redis://redis:6379/0}"
    # Extract host:port from redis://host:port/db
    local hostport
    hostport=$(echo "$url" | sed -E 's|redis://([^/]+).*|\1|')
    local host=${hostport%%:*}
    local port=${hostport##*:}
    port=${port:-6379}
    local retries=20
    echo "[entrypoint] Waiting for Redis at ${host}:${port} ..."
    until nc -z "$host" "$port" 2>/dev/null; do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            echo "[entrypoint] ERROR: Redis not reachable after 40 s"
            exit 1
        fi
        sleep 2
    done
    echo "[entrypoint] Redis is ready."
}

# ---------- Run migrations ----------------------------------------------------
run_migrations() {
    echo "[entrypoint] Running migrations ..."
    python manage.py migrate --noinput
    echo "[entrypoint] Migrations complete."
}

# ---------- Collect staticfiles -----------------------------------------------
collect_static() {
    echo "[entrypoint] Collecting static files ..."
    python manage.py collectstatic --noinput --clear 2>/dev/null || true
    echo "[entrypoint] Static files collected."
}

# ---------- Auto-create superuser ---------------------------------------------
create_superuser() {
    if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
        echo "[entrypoint] Ensuring superuser exists ..."
        python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
email = '${DJANGO_SUPERUSER_EMAIL}'
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        email=email,
        username='${DJANGO_SUPERUSER_USERNAME:-admin}',
        password='${DJANGO_SUPERUSER_PASSWORD}',
    )
    print(f'Superuser {email} created.')
else:
    print(f'Superuser {email} already exists.')
"
    fi
}

# =============================================================================
# Main dispatch
# =============================================================================

case "${1:-web}" in

  web)
    wait_for_db
    wait_for_redis
    run_migrations
    collect_static
    create_superuser
    echo "[entrypoint] Starting Gunicorn on 0.0.0.0:8000 ..."
    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-4}" \
        --threads "${GUNICORN_THREADS:-2}" \
        --timeout 300 \
        --graceful-timeout 30 \
        --max-requests 1000 \
        --max-requests-jitter 50 \
        --access-logfile - \
        --error-logfile - \
        --log-level info
    ;;

  daphne)
    wait_for_db
    wait_for_redis
    echo "[entrypoint] Starting Daphne (ASGI) on 0.0.0.0:9000 ..."
    exec daphne \
        -b 0.0.0.0 \
        -p 9000 \
        --access-log - \
        --proxy-headers \
        config.asgi:application
    ;;

  celery-worker)
    wait_for_db
    wait_for_redis
    echo "[entrypoint] Starting Celery worker ..."
    exec celery -A config worker \
        --loglevel=info \
        --concurrency="${CELERY_CONCURRENCY:-4}" \
        --max-tasks-per-child=200 \
        -Q celery,billing,payroll,notifications,emails
    ;;

  celery-beat)
    wait_for_db
    wait_for_redis
    echo "[entrypoint] Starting Celery Beat ..."
    exec celery -A config beat \
        --loglevel=info \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;

  *)
    exec "$@"
    ;;

esac
