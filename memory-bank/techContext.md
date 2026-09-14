# Technical Context

## Reusable analysis module

- shared/incidents_analysis/analysis.py is the source of truth for validation and metrics.
- Both script and API call the same functions to avoid duplicated logic.
- Validation includes country/carrier, tracking, category, description, email, status, closed-without-score, and score range rules.

## Script

- Entry point: scripts/analyze.py
- Usage: python scripts/analyze.py scripts/incidents-trackflow.csv
- Prints summary and asks whether to export results.csv.
- Export format: one row per metric with section, metric, value, percentage.

## Backend API

- Path: services/api/main.py
- Endpoints:
  - POST /api/incidents/analyze (multipart CSV upload, returns JSON summary)
  - GET /api/incidents/results/export (downloads last summary as CSV)
  - GET /suppliers with optional `country` and `category` filters
  - POST /suppliers
  - GET /suppliers/{id}
  - PATCH /suppliers/{id}/rate
  - PATCH /suppliers/{id}/status
  - DELETE /suppliers/{id}
- Health endpoint: GET /health
- Runtime dependencies pinned in services/api/requirements.txt:
  - fastapi==0.99.1
  - uvicorn==0.35.0
  - python-multipart==0.0.20
  - pydantic<2
  - starlette<0.28
  - tinydb==4.8.0
- Supplier directory files:
  - services/api/models.py
  - services/api/database.py
  - services/api/routes/suppliers.py
  - services/api/seed.py
- TinyDB persistence file is local runtime state under services/api/data/suppliers.json and is gitignored.
- App startup seeds the supplier directory idempotently from the TrackFlow context.
- Root pyproject.toml defines `seed = "services.api.seed:main"` for `uv run seed` on environments where `uv` is installed.

## Backoffice UI

- Operations launcher home: uis/backoffice/app/page.tsx
- Incident analysis app route: uis/backoffice/app/incident-file-analyzer/page.tsx
- Supplier directory route: uis/backoffice/app/suppliers/page.tsx
- Additional launcher routes for alignment with monorepo app directories:
  - uis/backoffice/app/website/page.tsx
  - uis/backoffice/app/talent-pipeline-tracker/page.tsx
- Homepage exposes a dropdown menu to choose among supplier directory, incident file analyzer, website, and talent pipeline tracker routes.
- Incident analyzer route provides file upload, summary visualization, invalid breakdown, and export button.
- Supplier directory route fetches from the API without full-page reloads, supports country/category filters, supplier registration, rate updates, and active/suspended status badges.
- API base URL from NEXT_PUBLIC_INCIDENTS_API_BASE_URL (defaults to http://localhost:8000).
