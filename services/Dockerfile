# ======================================================================
# TrackFlow monorepo — API services container (FastAPI)
#
# Build context MUST be the repository root.
#
# Development (docker compose up):
#   Bind‑mount the repo → /app for hot reload via uvicorn --reload.
#
# Production:
#   Remove `--reload` or override CMD in a production compose overlay.
# ======================================================================
FROM python:3.12-slim

WORKDIR /app

# ------------------------------------------------------------------
# 1. Install OS-level build/runtime deps
# ------------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# 2. Copy dependency manifests & install (layer caching)
# ------------------------------------------------------------------
COPY services/api/requirements.txt services/api/requirements.txt
COPY pyproject.toml .

# Prefer pip install from requirements.txt for reproducibility.
# Also install the project in editable mode so `services` and `packages`
# and `shared` resolve via sys.path (same as the local dev flow).
RUN pip install --no-cache-dir -r services/api/requirements.txt

# ------------------------------------------------------------------
# 3. Copy the rest of the monorepo source
#    (overridden by compose bind‑mount in dev)
# ------------------------------------------------------------------
COPY . .

# ------------------------------------------------------------------
# 4. PYTHONPATH – matches the local dev convention
#     pyproject.toml already sets pythonpath = ["."] for pytest,
#     but the runtime also needs the repo root to resolve imports.
# ------------------------------------------------------------------
ENV PYTHONPATH=/app

EXPOSE 8000

# Default: production-ready invocation (no reload).
# Override CMD in docker-compose.dev.yml for hot reload.
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]