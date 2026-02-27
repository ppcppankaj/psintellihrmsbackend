# =============================================================================
# PS IntelliHR — Production Dockerfile (multi-stage)
# Stage 1: Builder — install deps, collectstatic
# Stage 2: Runtime — lean image with gunicorn + daphne
# =============================================================================

# ---------- Stage 1: Builder -------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# System deps needed for psycopg2, WeasyPrint, Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/base.txt
COPY requirements/production.txt requirements/production.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements/production.txt


# ---------- Stage 2: Runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# Only runtime libraries — no compilers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libjpeg62-turbo \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system hrms \
    && adduser --system --ingroup hrms hrms

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Collect static (runs with a dummy SECRET_KEY so it never fails)
RUN SECRET_KEY=collectstatic-dummy \
    DATABASE_URL=sqlite:///tmp.db \
    python manage.py collectstatic --noinput 2>/dev/null || true

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/logs /app/media \
    && chown -R hrms:hrms /app/logs /app/media

EXPOSE 8000

USER hrms

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
CMD ["web"]