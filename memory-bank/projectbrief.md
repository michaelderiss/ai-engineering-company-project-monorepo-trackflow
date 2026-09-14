# Project Brief

## Current focus

Implement two active TrackFlow milestones:

1. Incident analysis workflow in scripts/, services/api, and uis/backoffice
2. Supplier directory with TinyDB-backed API, seeder, and backoffice UI

## Business objective

- Provide Valentina Cruz (CX) with reliable incident-volume, quality, category, status, country, and satisfaction metrics without exposing sensitive customer emails.
- Provide Carlos Vega and Ana Whitfield with a centralized supplier directory across USA and Spain, including filtering, registration, rate updates, and suspension controls.

## Deliverable scope added

- scripts/analyze.py CLI for CSV analysis and optional export.
- scripts/incidents-company.csv and scripts/incidents-trackflow.csv as test fixtures.
- shared/incidents_analysis reusable module used by script and API.
- services/api endpoints for upload analysis and CSV export.
- uis/backoffice incident analysis page for upload, summary, and export.
- services/api TinyDB supplier directory backend with startup seeding and CRUD/filter routes.
- pyproject.toml script entry for `seed` to support `uv run seed` when `uv` is available.
- uis/backoffice supplier directory page with filters, registration form, rate update, and status toggle.
