# TrackFlow Backoffice

Internal logistics operations entry view for TrackFlow.

## Purpose

This app starts the internal `uis/backoffice` surface with a company-relevant route (`/`) that imports generated Milestone 2 output and displays warehouse assignment, carrier recommendation, and expected delivery windows.

Output source order used by `uis/backoffice/lib/milestone2.ts`:

1. `.trackflow-milestone2-output.json`
2. `.trackflow-dummy-order.txt` (fallback)

Artifacts are auto-generated from `src/milestone2-output.js` through `scripts/generate_milestone2_output.cjs`.

## Tech

- Next.js App Router
- React
- TypeScript

## Run locally

```bash
cd uis/backoffice
npm install
npm run dev
```

`npm run dev` and `npm run build` automatically run `npm run milestone2:sync` first.

Open `http://localhost:3000`.

## Scope note

If this UI starts depending on real APIs or workers, add those backend services under `/services` following `services/README.md`.
