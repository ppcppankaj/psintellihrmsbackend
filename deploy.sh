#!/bin/bash
# =============================================================================
# PS IntelliHR — Production Deployment Script
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                   # Full first-time deploy
#   ./deploy.sh --update          # Rebuild & restart (no SSL)
#   ./deploy.sh --ssl-only        # Just obtain/renew SSL certificates
#   ./deploy.sh --down            # Shut everything down
# =============================================================================

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------- Pre-flight checks ------------------------------------------------

preflight() {
    command -v docker >/dev/null 2>&1    || error "docker is not installed"
    command -v docker compose >/dev/null 2>&1 || error "docker compose (v2) is not installed"
    [ -f "$PROJECT_DIR/.env" ]           || error ".env file not found. Copy .env.example → .env and configure."
    info "Pre-flight checks passed."
}

# ---------- SSL / Certbot ----------------------------------------------------

obtain_ssl() {
    # Source .env for DOMAIN
    set -a; source "$PROJECT_DIR/.env"; set +a
    local domain="${BASE_DOMAIN:?BASE_DOMAIN not set in .env}"

    info "Obtaining SSL certificate for ${domain} ..."

    # Start nginx temporarily with self-signed or http-only config
    # so Certbot can access /.well-known/acme-challenge/
    docker compose -f "$COMPOSE_FILE" up -d nginx

    docker compose -f "$COMPOSE_FILE" run --rm certbot \
        certbot certonly \
        --webroot \
        -w /var/www/certbot \
        -d "$domain" \
        -d "*.$domain" \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@$domain}" \
        --agree-tos \
        --no-eff-email \
        --force-renewal

    info "SSL certificate obtained. Restarting nginx ..."
    docker compose -f "$COMPOSE_FILE" restart nginx
}

# ---------- Build & Deploy ---------------------------------------------------

full_deploy() {
    info "============================================="
    info "  PS IntelliHR — Full Production Deployment"
    info "============================================="

    # 1. Create required directories
    mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/media" "$PROJECT_DIR/staticfiles"

    # 2. Build all images
    info "Building Docker images ..."
    docker compose -f "$COMPOSE_FILE" build --no-cache

    # 3. Start infrastructure first (postgres, redis)
    info "Starting database and Redis ..."
    docker compose -f "$COMPOSE_FILE" up -d postgres redis
    sleep 10

    # 4. Start application services
    info "Starting application services ..."
    docker compose -f "$COMPOSE_FILE" up -d

    # 5. Wait for web health check
    info "Waiting for web service to become healthy ..."
    local retries=30
    until docker compose -f "$COMPOSE_FILE" exec web curl -sf http://localhost:8000/api/v1/health/ >/dev/null 2>&1; do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            warn "Health check timed out but services may still be starting."
            break
        fi
        sleep 5
    done

    info "============================================="
    info "  Deployment complete!"
    info ""
    info "  Services running:"
    docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    info ""
    info "  Next steps:"
    info "  1. Run './deploy.sh --ssl-only' to obtain SSL certificates"
    info "  2. Update nginx/conf.d/default.conf with your domain"
    info "  3. Configure DNS: A record → server IP"
    info "  4. Configure wildcard DNS for tenant subdomains"
    info "============================================="
}

update_deploy() {
    info "Rebuilding and restarting services ..."
    docker compose -f "$COMPOSE_FILE" build
    docker compose -f "$COMPOSE_FILE" up -d
    info "Update complete."
    docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}"
}

shutdown() {
    info "Shutting down all services ..."
    docker compose -f "$COMPOSE_FILE" down
    info "All services stopped."
}

# ---------- Firewall setup (Linux only) --------------------------------------

setup_firewall() {
    if command -v ufw >/dev/null 2>&1; then
        info "Configuring UFW firewall ..."
        sudo ufw allow 22/tcp    comment "SSH"
        sudo ufw allow 80/tcp    comment "HTTP"
        sudo ufw allow 443/tcp   comment "HTTPS"
        sudo ufw --force enable
        sudo ufw status
    else
        warn "UFW not found. Ensure ports 22, 80, 443 are open in your cloud security group."
    fi
}

# ---------- Main dispatch ----------------------------------------------------

cd "$PROJECT_DIR"
preflight

case "${1:-}" in
    --ssl-only)   obtain_ssl ;;
    --update)     update_deploy ;;
    --down)       shutdown ;;
    --firewall)   setup_firewall ;;
    *)            full_deploy ;;
esac
