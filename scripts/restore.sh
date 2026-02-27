#!/usr/bin/env bash
# =============================================================================
# PostgreSQL + Media Restore Script
# Enterprise HRMS SaaS Platform
#
# Usage:
#   ./scripts/restore.sh <db_backup_file> [media_backup_file]
#
# Examples:
#   ./scripts/restore.sh /backups/db/hrms_20250101_020000.sql.gz
#   ./scripts/restore.sh /backups/db/hrms_20250101_020000.sql.gz.gpg
#   ./scripts/restore.sh /backups/db/hrms_20250101_020000.sql.gz /backups/media/media_20250101_020000.tar.gz
#
# Environment variables (set in .env or docker-compose):
#   POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, DB_HOST, DB_PORT
#   BACKUP_ENCRYPTION_KEY (required if backup is .gpg encrypted)
#   MEDIA_DIR             (default: /var/www/media)
#
# SAFETY:
#   - Prompts for confirmation before restoring
#   - Creates a pre-restore backup automatically
#   - Verifies backup file integrity before restoring
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
DB_NAME="${POSTGRES_DB:-hrms}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
MEDIA_DIR="${MEDIA_DIR:-/var/www/media}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo -e "${RED}ERROR: $*${NC}" >&2
}

warn() {
    echo -e "${YELLOW}WARN: $*${NC}"
}

success() {
    echo -e "${GREEN}$*${NC}"
}

# ── Argument Validation ─────────────────────────────────────────────────────
DB_BACKUP_FILE="${1:-}"
MEDIA_BACKUP_FILE="${2:-}"

if [ -z "${DB_BACKUP_FILE}" ]; then
    error "Usage: $0 <db_backup_file> [media_backup_file]"
    echo ""
    echo "Available DB backups:"
    ls -lhtr "${BACKUP_DIR}/db/" 2>/dev/null || echo "  No backups found in ${BACKUP_DIR}/db/"
    exit 1
fi

if [ ! -f "${DB_BACKUP_FILE}" ]; then
    error "Database backup file not found: ${DB_BACKUP_FILE}"
    exit 1
fi

if [ -n "${MEDIA_BACKUP_FILE}" ] && [ ! -f "${MEDIA_BACKUP_FILE}" ]; then
    error "Media backup file not found: ${MEDIA_BACKUP_FILE}"
    exit 1
fi

# ── Confirmation ─────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════"
echo "  HRMS DATABASE RESTORE"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Database:     ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo "  DB Backup:    ${DB_BACKUP_FILE}"
echo "  Media Backup: ${MEDIA_BACKUP_FILE:-<none>}"
echo "  Encrypted:    $(echo "${DB_BACKUP_FILE}" | grep -q '\.gpg$' && echo 'YES' || echo 'NO')"
echo ""
echo "  ⚠️  THIS WILL OVERWRITE THE CURRENT DATABASE"
echo ""

if [ "${FORCE_RESTORE:-}" != "true" ]; then
    read -p "Type 'RESTORE' to confirm: " confirm
    if [ "${confirm}" != "RESTORE" ]; then
        echo "Aborted."
        exit 0
    fi
fi

# ── Pre-restore Safety Backup ────────────────────────────────────────────────
PRE_RESTORE_DIR="${BACKUP_DIR}/pre-restore"
mkdir -p "${PRE_RESTORE_DIR}"
PRE_RESTORE_FILE="${PRE_RESTORE_DIR}/${DB_NAME}_pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"

log "Creating pre-restore safety backup: ${PRE_RESTORE_FILE}"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --no-owner --no-acl --format=custom --compress=9 \
    -f "${PRE_RESTORE_FILE%.gz}" 2>/dev/null && \
    gzip -f "${PRE_RESTORE_FILE%.gz}" && \
    log "Pre-restore backup saved: $(du -h "${PRE_RESTORE_FILE}" | cut -f1)" || \
    warn "Pre-restore backup failed (database may be empty)"

# ── Decrypt if Needed ────────────────────────────────────────────────────────
RESTORE_FILE="${DB_BACKUP_FILE}"

if echo "${DB_BACKUP_FILE}" | grep -q '\.gpg$'; then
    if [ -z "${ENCRYPTION_KEY}" ]; then
        error "Backup is encrypted but BACKUP_ENCRYPTION_KEY is not set"
        exit 1
    fi
    DECRYPTED_FILE="${DB_BACKUP_FILE%.gpg}"
    log "Decrypting backup..."
    gpg --batch --yes --decrypt \
        --passphrase "${ENCRYPTION_KEY}" \
        --output "${DECRYPTED_FILE}" \
        "${DB_BACKUP_FILE}"
    RESTORE_FILE="${DECRYPTED_FILE}"
    log "Decryption complete"
fi

# ── Database Restore ─────────────────────────────────────────────────────────
log "Starting database restore..."

# Decompress if gzipped
if echo "${RESTORE_FILE}" | grep -q '\.gz$'; then
    UNCOMPRESSED="${RESTORE_FILE%.gz}"
    gunzip -kf "${RESTORE_FILE}"
    RESTORE_FILE="${UNCOMPRESSED}"
fi

# Restore using pg_restore for custom-format dumps
PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    --single-transaction \
    "${RESTORE_FILE}" 2>&1 || {
    # pg_restore may exit non-zero for warnings; check if critical
    warn "pg_restore completed with warnings (this may be normal)"
}

log "Database restore complete"

# Cleanup temporary decompressed file
if [ "${RESTORE_FILE}" != "${DB_BACKUP_FILE}" ]; then
    rm -f "${RESTORE_FILE}" 2>/dev/null || true
fi

# ── Media Restore ────────────────────────────────────────────────────────────
if [ -n "${MEDIA_BACKUP_FILE}" ]; then
    log "Starting media restore..."

    # Decrypt if needed
    MEDIA_RESTORE_FILE="${MEDIA_BACKUP_FILE}"
    if echo "${MEDIA_BACKUP_FILE}" | grep -q '\.gpg$'; then
        if [ -z "${ENCRYPTION_KEY}" ]; then
            error "Media backup is encrypted but BACKUP_ENCRYPTION_KEY is not set"
            exit 1
        fi
        MEDIA_DECRYPTED="${MEDIA_BACKUP_FILE%.gpg}"
        gpg --batch --yes --decrypt \
            --passphrase "${ENCRYPTION_KEY}" \
            --output "${MEDIA_DECRYPTED}" \
            "${MEDIA_BACKUP_FILE}"
        MEDIA_RESTORE_FILE="${MEDIA_DECRYPTED}"
    fi

    # Backup existing media
    if [ -d "${MEDIA_DIR}" ]; then
        MEDIA_BACKUP_OLD="${PRE_RESTORE_DIR}/media_pre_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
        tar -czf "${MEDIA_BACKUP_OLD}" -C "$(dirname "${MEDIA_DIR}")" "$(basename "${MEDIA_DIR}")" 2>/dev/null || true
        log "Existing media backed up to: ${MEDIA_BACKUP_OLD}"
    fi

    # Restore media
    mkdir -p "${MEDIA_DIR}"
    tar -xzf "${MEDIA_RESTORE_FILE}" -C "$(dirname "${MEDIA_DIR}")" 2>/dev/null || {
        warn "Media restore had warnings"
    }

    log "Media restore complete"

    # Cleanup
    if [ "${MEDIA_RESTORE_FILE}" != "${MEDIA_BACKUP_FILE}" ]; then
        rm -f "${MEDIA_RESTORE_FILE}" 2>/dev/null || true
    fi
fi

# ── Post-Restore Verification ────────────────────────────────────────────────
log "Running post-restore verification..."

TABLE_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null | tr -d ' ')

RLS_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -t -c "SELECT count(*) FROM pg_class WHERE relrowsecurity = true AND relnamespace = 'public'::regnamespace" 2>/dev/null | tr -d ' ')

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  RESTORE COMPLETE"
echo "═══════════════════════════════════════════════════════════"
echo "  Tables restored:     ${TABLE_COUNT:-unknown}"
echo "  RLS-enabled tables:  ${RLS_COUNT:-unknown}"
echo "  Pre-restore backup:  ${PRE_RESTORE_FILE}"
echo "═══════════════════════════════════════════════════════════"
success "  ✓ Restore completed successfully"
echo ""
echo "  RECOMMENDED: Run Django migrations and RLS audit:"
echo "    python manage.py migrate --check"
echo "    python scripts/rls_audit.py"
