# ======================================================================
# TrackFlow monorepo — API services container (FastAPI)
#
# Build context MUST be the repository root.
#
# Based on the official Python image. Installs `uv` (the Astral package
# manager) and installs dependencies from requirements.txt with
# `uv pip install`. Development runs uvicorn with --reload for hot
# reload via the compose bind mount.
# ======================================================================
FROM python:3.12-slim

WORKDIR /app

# ------------------------------------------------------------------
# 1. Install OS-level build/runtime deps
# ------------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# 2. Install uv (Astral's fast Python package installer)
# ------------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ------------------------------------------------------------------
# 3. Copy dependency manifests & install (layer caching)
#     - The ticket specifies `uv pip install -r requirements.txt`,
#       so use that.
#     - pyproject.toml has no [build-system], so we skip `pip install
#       -e .`; imports resolve via PYTHONPATH=/app below (same as the
#       local dev flow).
# ------------------------------------------------------------------
COPY services/api/requirements.txt services/api/requirements.txt
COPY pyproject.toml .

ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_SYSTEM_PYTHON=1

RUN uv pip install -r services/api/requirements.txt

# ------------------------------------------------------------------
# 4. Copy the rest of the monorepo source
#    (overridden by compose bind‑mount in dev)
# ------------------------------------------------------------------
COPY . .

# ------------------------------------------------------------------
# 5. PYTHONPATH – matches the local dev convention
#     pyproject.toml already sets pythonpath = ["."] for pytest,
#     but the runtime also needs the repo root to resolve imports.
# ------------------------------------------------------------------
ENV PYTHONPATH=/app

EXPOSE 8000

# Default: development invocation with hot reload (uvicorn --reload).
# Override CMD in the production overlay to disable --reload.
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]