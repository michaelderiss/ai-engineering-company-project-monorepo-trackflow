#!/bin/sh
# ======================================================================
# TrackFlow UI start script
#
# Starts BOTH Next.js applications inside ONE container:
#   - website   → :3000 (default, override WEBSITE_PORT)
#   - backoffice → :3001 (default, override BACKOFFICE_PORT)
#
# Development (default, docker compose up):
#   Runs `next dev` for both apps — hot reload, bind mount edits are
#   reflected in the browser without rebuilding the image.
#
# Production (TRACKFLOW_UI_MODE=prod):
#   Runs `next build && next start` for both apps first.
#
# Uses trap for clean shutdown on SIGTERM/SIGINT.
# ======================================================================

set -e

MODE="${TRACKFLOW_UI_MODE:-dev}"
WEBSITE_PORT="${WEBSITE_PORT:-3000}"
BACKOFFICE_PORT="${BACKOFFICE_PORT:-3001}"

echo "==> TrackFlow UI (mode: ${MODE})"

if [ "${MODE}" = "prod" ]; then
  echo "==> Building website..."
  npm --prefix uis/website run build
  echo "==> Building backoffice..."
  npm --prefix uis/backoffice run build
  echo "==> Starting website (prod) on ${WEBSITE_PORT}..."
  npm --prefix uis/website run start -- -p "${WEBSITE_PORT}" &
  WEBSITE_PID=$!
  echo "==> Starting backoffice (prod) on ${BACKOFFICE_PORT}..."
  npm --prefix uis/backoffice run start -- -p "${BACKOFFICE_PORT}" &
  BACKOFFICE_PID=$!
else
  echo "==> Starting website (dev) on ${WEBSITE_PORT}..."
  npm --prefix uis/website run dev -- -p "${WEBSITE_PORT}" &
  WEBSITE_PID=$!
  echo "==> Starting backoffice (dev) on ${BACKOFFICE_PORT}..."
  npm --prefix uis/backoffice run dev -- -p "${BACKOFFICE_PORT}" &
  BACKOFFICE_PID=$!
fi

# Trap for clean shutdown
cleanup() {
    echo "==> Shutting down..."
    kill "$WEBSITE_PID" "$BACKOFFICE_PID" 2>/dev/null || true
    wait "$WEBSITE_PID" "$BACKOFFICE_PID" 2>/dev/null || true
    echo "==> Done."
}
trap cleanup INT TERM

echo "==> Both UI apps running. Press Ctrl+C to stop."
wait