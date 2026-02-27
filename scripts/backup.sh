#!/usr/bin/env bash
# =============================================================================
# PostgreSQL + Media Backup Script
# Enterprise HRMS SaaS Platform
#
# Usage:
#   ./scripts/backup.sh              # Full backup (DB + media)
#   ./scripts/backup.sh --db-only    # Database only
#   ./scripts/backup.sh --media-only # Media only
#
# Environment variables (set in .env or docker-compose):
#   POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, DB_HOST, DB_PORT
#   BACKUP_DIR           (default: /backups)
#   BACKUP_RETENTION_DAYS (default: 30)
#   S3_BACKUP_BUCKET     (optional: s3://bucket-name for offsite)
#   BACKUP_ENCRYPTION_KEY (optional: GPG symmetric passphrase)
#   BACKUP_WEBHOOK_URL   (optional: Slack/Teams webhook for failure alerts)
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_NAME="${POSTGRES_DB:-hrms}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
MEDIA_DIR="${MEDIA_DIR:-/var/www/media}"
S3_BUCKET="${S3_BACKUP_BUCKET:-}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
WEBHOOK_URL="${BACKUP_WEBHOOK_URL:-}"

# Ensure backup directories exist
mkdir -p "${BACKUP_DIR}/db" "${BACKUP_DIR}/media" "${BACKUP_DIR}/logs"

LOG_FILE="${BACKUP_DIR}/logs/backup_${TIMESTAMP}.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

alert_failure() {
    local message="$1"
    log "ALERT: ${message}"
    if [ -n "${WEBHOOK_URL}" ]; then
        curl -s -X POST -H 'Content-Type: application/json' \
            -d "{\"text\":\"🚨 HRMS Backup FAILED: ${message} ($(hostname) at $(date))\"}" \
            "${WEBHOOK_URL}" >/dev/null 2>&1 || true
    fi
}

encrypt_file() {
    local input_file="$1"
    if [ -n "${ENCRYPTION_KEY}" ] && command -v gpg >/dev/null 2>&1; then
        log "Encrypting ${input_file}"
        gpg --batch --yes --symmetric --cipher-algo AES256 \
            --passphrase "${ENCRYPTION_KEY}" \
            --output "${input_file}.gpg" \
            "${input_file}"
        rm -f "${input_file}"
        log "Encrypted: ${input_file}.gpg"
    fi
}

# ── Database Backup ──────────────────────────────────────────────────────────
backup_database() {
    local dump_file="${BACKUP_DIR}/db/${DB_NAME}_${TIMESTAMP}.sql.gz"
    log "Starting database backup: ${dump_file}"

    PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --no-owner \
        --no-acl \
        --format=custom \
        --compress=9 \
        -f "${dump_file%.gz}"

    # Compress with gzip for additional savings
    if [ -f "${dump_file%.gz}" ]; then
        gzip -f "${dump_file%.gz}"
        log "Database backup complete: $(du -h "${dump_file}" | cut -f1)"
        encrypt_file "${dump_file}"
    else
        alert_failure "Database dump file not created"
        return 1
    fi
}

# ── Media Backup ─────────────────────────────────────────────────────────────
backup_media() {
    local archive="${BACKUP_DIR}/media/media_${TIMESTAMP}.tar.gz"
    log "Starting media backup: ${archive}"

    if [ -d "${MEDIA_DIR}" ]; then
        tar -czf "${archive}" -C "$(dirname "${MEDIA_DIR}")" "$(basename "${MEDIA_DIR}")" 2>/dev/null || true
        log "Media backup complete: $(du -h "${archive}" | cut -f1)"
        encrypt_file "${archive}"
    else
        log "WARN: Media directory ${MEDIA_DIR} not found, skipping"
    fi
}

# ── S3 Upload (optional) ────────────────────────────────────────────────────
upload_to_s3() {
    if [ -n "${S3_BUCKET}" ]; then
        log "Uploading backups to S3: ${S3_BUCKET}"
        aws s3 sync "${BACKUP_DIR}/db/" "${S3_BUCKET}/db/" --storage-class STANDARD_IA 2>&1 | tee -a "${LOG_FILE}"
        aws s3 sync "${BACKUP_DIR}/media/" "${S3_BUCKET}/media/" --storage-class STANDARD_IA 2>&1 | tee -a "${LOG_FILE}"
        log "S3 upload complete"
    fi
}

# ── Retention Cleanup ────────────────────────────────────────────────────────
cleanup_old_backups() {
    log "Cleaning backups older than ${RETENTION_DAYS} days"
    find "${BACKUP_DIR}/db/" -name "*.gz" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
    find "${BACKUP_DIR}/media/" -name "*.tar.gz" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
    find "${BACKUP_DIR}/logs/" -name "*.log" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
    log "Cleanup complete"
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    log "=== HRMS Backup Started ==="

    # Trap errors and alert
    trap 'alert_failure "Backup script failed at line $LINENO"' ERR

    case "${1:-all}" in
        --db-only)
            backup_database
            ;;
        --media-only)
            backup_media
            ;;
        *)
            backup_database
            backup_media
            ;;
    esac

    upload_to_s3
    cleanup_old_backups

    log "=== HRMS Backup Completed ==="
}

main "$@"
