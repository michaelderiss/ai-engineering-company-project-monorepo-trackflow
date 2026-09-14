# Project Brief

## Current focus

Implement the TrackFlow incidents analysis milestone in two phases:

1. Script-first validation in scripts/
2. Shared logic reuse in backend API and backoffice UI

## Business objective

Provide Valentina Cruz (CX) with reliable incident-volume, quality, category, status, country, and satisfaction metrics without exposing sensitive customer emails.

## Deliverable scope added

- scripts/analyze.py CLI for CSV analysis and optional export.
- scripts/incidents-company.csv and scripts/incidents-trackflow.csv as test fixtures.
- shared/incidents_analysis reusable module used by script and API.
- services/api endpoints for upload analysis and CSV export.
- uis/backoffice incident analysis page for upload, summary, and export.
