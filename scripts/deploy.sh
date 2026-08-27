#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# FinSentry AI — Production Deployment Script
# ──────────────────────────────────────────────────────────────
# Usage:
#   ./scripts/deploy.sh          → Build & deploy all services
#   ./scripts/deploy.sh --build  → Force rebuild images
#   ./scripts/deploy.sh --down   → Stop all services
#   ./scripts/deploy.sh --logs   → Tail logs
#   ./scripts/deploy.sh --status → Show running services
# ──────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/docker-compose.prod.yml"
PROJECT_NAME="finsentry"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Pre-flight Checks ───────────────────────────────────────
preflight() {
    log_info "Running pre-flight checks..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH."
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running."
        exit 1
    fi

    if [ ! -f "${PROJECT_ROOT}/backend/.env" ]; then
        log_error "Missing backend/.env — copy from .env.example and fill in secrets."
        exit 1
    fi

    log_ok "Pre-flight checks passed."
}

# ── Commands ─────────────────────────────────────────────────
deploy() {
    preflight
    local build_flag="${1:-}"

    log_info "Deploying FinSentry AI (production)..."

    if [ "$build_flag" = "--build" ]; then
        log_info "Force-rebuilding images..."
        docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" build --no-cache
    fi

    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d --build

    log_info "Waiting for services to become healthy..."
    sleep 10

    show_status
    log_ok "Deployment complete."
}

stop() {
    log_info "Stopping FinSentry AI..."
    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down
    log_ok "All services stopped."
}

show_logs() {
    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs -f --tail=100
}

show_status() {
    echo ""
    log_info "Service Status:"
    echo "────────────────────────────────────────────────────"
    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps
    echo "────────────────────────────────────────────────────"
    echo ""

    # Health check
    if curl -sf http://localhost:80/api/v1/health > /dev/null 2>&1; then
        log_ok "Gateway health check: PASSED"
    else
        log_warn "Gateway health check: PENDING (services may still be starting)"
    fi
}

# ── Entry Point ──────────────────────────────────────────────
case "${1:-deploy}" in
    --down|down|stop)
        stop
        ;;
    --logs|logs)
        show_logs
        ;;
    --status|status)
        show_status
        ;;
    --build)
        deploy "--build"
        ;;
    deploy|*)
        deploy ""
        ;;
esac
