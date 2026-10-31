#!/usr/bin/env bash
# ======================================================================
# TrackFlow — Production deploy script
#
# Usage:
#   bash scripts/deploy.sh
#
# Prerequisites (run once on the VPS):
#   1. Install Docker + Docker Compose (v2)
#   2. git clone <repo-url> /opt/trackflow
#   3. cd /opt/trackflow && cp .env.docker .env
#   4. Edit .env with real production values:
#      - JWT_SECRET_KEY (generate: openssl rand -hex 32)
#      - DATABASE_URL  (real Supabase Postgres URL)
#      - RESEND_API_KEY / RESEND_FROM_EMAIL
#      - CORS_ORIGINS  (public domain or IP where the UIs are served)
#      - TRACKFLOW_UI_MODE=prod  (build+serve instead of dev hot reload)
#      - BACKEND_UPSTREAM  (defaults to http://api:8000 — service name
#        inside the Docker network; no localhost required)
#   5. Run this deploy script
#
# What this script does:
#   - Pulls the latest code
#   - Builds production Docker images
#   - Starts all services in detached mode
#   - Shows service status
# ======================================================================

set -euo pipefail

REPO_DIR="${1:-/opt/trackflow}"
COMPOSE_CMD="docker compose -f ${REPO_DIR}/docker-compose.yml -f ${REPO_DIR}/docker-compose.prod.yml"

echo "========================================"
echo "  TrackFlow — Production Deploy"
echo "========================================"

cd "${REPO_DIR}" || { echo "ERROR: ${REPO_DIR} not found"; exit 1; }

# 1. Pull latest code
echo ""
echo "[1/4] Pulling latest code..."
git pull

# 2. Build production images
echo ""
echo "[2/4] Building production Docker images..."
${COMPOSE_CMD} build --pull

# 3. Start services
echo ""
echo "[3/4] Starting services..."
${COMPOSE_CMD} up -d --remove-orphans

# 4. Show status
echo ""
echo "[4/4] Service status:"
${COMPOSE_CMD} ps

echo ""
echo "========================================"
echo "  Deploy complete!"
echo ""
echo "  API:         http://$(hostname -I | awk '{print $1}'):8000/health"
echo "  Backoffice:  http://$(hostname -I | awk '{print $1}'):3001"
echo "  Website:     http://$(hostname -I | awk '{print $1}'):3000"
echo ""
echo "  Logs:        ${COMPOSE_CMD} logs -f"
echo "  Restart:     ${COMPOSE_CMD} restart"
echo "  Stop:        ${COMPOSE_CMD} down"
echo "========================================"