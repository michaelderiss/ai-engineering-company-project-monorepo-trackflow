#!/bin/sh
# ======================================================================
# TrackFlow UI development start script
#
# Runs both Next.js development servers in parallel inside one container.
# Uses trap for clean shutdown on SIGTERM/SIGINT.
#
# For production deployments, use the separate `docker compose -f
# docker-compose.prod.yml` which builds and serves each app individually.
# ======================================================================

set -e

BACKOFFICE_PORT="${BACKOFFICE_PORT:-3000}"
WEBSITE_PORT="${WEBSITE_PORT:-3001}"

echo "==> Starting backoffice on port ${BACKOFFICE_PORT} ..."
npm --prefix uis/backoffice run dev -- -p "${BACKOFFICE_PORT}" &
BACKOFFICE_PID=$!

echo "==> Starting website on port ${WEBSITE_PORT} ..."
npm --prefix uis/website run dev -- -p "${WEBSITE_PORT}" &
WEBSITE_PID=$!

# Trap for clean shutdown
cleanup() {
    echo "==> Shutting down..."
    kill "$BACKOFFICE_PID" "$WEBSITE_PID" 2>/dev/null
    wait "$BACKOFFICE_PID" "$WEBSITE_PID" 2>/dev/null
    echo "==> Done."
}
trap cleanup INT TERM

echo "==> Both UI servers running. Press Ctrl+C to stop."
wait