# ======================================================================
# TrackFlow monorepo — UI container image (Next.js apps)
#
# One image, two use-cases (dev and prod):
#
# Development (docker compose up):
#   Bind-mount the full repo → /app for instant hot reload. Volumes
#   preserve node_modules so the host OS does not shadow the
#   Linux-compiled binaries. CMD runs `npm run dev`.
#
# Production (docker compose -f docker-compose.prod.yml up):
#   The CMD runs `npm run build && npm run start` so the Next.js
#   standalone server serves pre-built output. No bind-mounts needed;
#   the image is self-contained.
# ======================================================================

FROM node:22-alpine

WORKDIR /app

# ------------------------------------------------------------------
# 1. Copy package manifests (layer caching)
# ------------------------------------------------------------------
COPY uis/website/package.json       uis/website/package-lock.json   ./uis/website/
COPY uis/backoffice/package.json    uis/backoffice/package-lock.json ./uis/backoffice/

# ------------------------------------------------------------------
# 2. Install dependencies for BOTH Next.js apps
# ------------------------------------------------------------------
RUN npm --prefix uis/website    ci && \
    npm --prefix uis/backoffice ci

# ------------------------------------------------------------------
# 3. Copy source code
# ------------------------------------------------------------------
COPY . .

EXPOSE 3000 3001

# Default: backoffice dev server (overridden in compose for website)
CMD ["npm", "--prefix", "uis/backoffice", "run", "dev"]