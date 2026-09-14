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
- Health endpoint: GET /health
- Runtime dependencies pinned in services/api/requirements.txt:
  - fastapi==0.99.1
  - uvicorn==0.35.0
  - python-multipart==0.0.20
  - pydantic<2
  - starlette<0.28

## Backoffice UI

- Operations launcher home: uis/backoffice/app/page.tsx
- Incident analysis app route: uis/backoffice/app/incident-file-analyzer/page.tsx
- Additional launcher routes for alignment with monorepo app directories:
  - uis/backoffice/app/website/page.tsx
  - uis/backoffice/app/talent-pipeline-tracker/page.tsx
- Homepage exposes a dropdown menu to choose among the three app entries and open the selected route.
- Incident analyzer route provides file upload, summary visualization, invalid breakdown, and export button.
- API base URL from NEXT_PUBLIC_INCIDENTS_API_BASE_URL (defaults to http://localhost:8000).
