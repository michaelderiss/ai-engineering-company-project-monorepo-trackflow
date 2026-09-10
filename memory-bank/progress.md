# Progress

## Current phase

Milestone 2 implementation plus feedback remediation.

The repository has moved beyond pure setup: core logistics utility functions now exist in `src/` and both UI targets (`uis/website`, `uis/backoffice`) were updated to address teacher feedback.

## What is now true

- The `src/` area now includes Milestone 2 TypeScript domain models and utility modules:
	- `src/types/models.ts`
	- `src/utils/collections.ts`
	- `src/utils/search.ts`
	- `src/utils/transformations.ts`
	- `src/utils/validations.ts`
	- `src/index.ts` barrel exports
	- `src/demo.ts` execution/demo script
- A Milestone 2 browser testing surface now exists in `src/index.html` with controller logic in `src/testing-interface.js`.
- Milestone 2 output generation is now shared through `src/milestone2-output.js` and exposed in the testing interface via a dedicated "Generate Milestone 2 Output" action.
- Milestone 2 sync artifacts are now generated from the same data source used by the testing interface (`src/testing-interface.js`), not from a separate embedded default dataset.
- The public site under `uis/website` now includes Milestone 1 structural sections (header/navigation, contact section, and footer) and has been migrated to TypeScript app files.
- The static milestone page `src/TrackFlow.html` now has explicit clickable nav targets for Header (`#header`), Nav (`#nav`), and Footer (`#footer`), while keeping Apply linked to `application.html`.
- The internal app under `uis/backoffice` has been migrated to TypeScript app files.
- Backoffice route `/` now imports and renders generated Milestone 2 output via `uis/backoffice/lib/milestone2.ts` using `.trackflow-milestone2-output.json` sourced from the testing-interface dataset.
- Both `uis/website` and `uis/backoffice` now include TypeScript toolchain files and scripts (`tsconfig.json`, `next-env.d.ts`, `typecheck`).
- `uis/backoffice` now auto-syncs Milestone 2 output before `dev` and `build` through `npm run milestone2:sync`.

## Feedback status snapshot

- Feedback point 1 (website missing Milestone 1 sections): addressed in `uis/website/app/page.tsx` and `uis/website/app/globals.css`.
- Feedback point 2 (apps were JavaScript, not TypeScript): addressed in both apps.
- Feedback point 3 (backoffice recomputed carrier logic inline): addressed by generated-output import flow from `src` helper logic through artifacts consumed in `uis/backoffice/lib/milestone2.ts` and display in `uis/backoffice/app/page.tsx`.
- Backoffice wording now reflects this source explicitly, and the section title is `Milestone 2 Output Snapshot`.

## Existing repo reality still relevant

- `uis/talent-pipeline-tracker` still exists as a separate, recruitment-domain app and can still cause domain drift if new work is not explicitly targeted.
- `packages/shared` still has placeholder shared types; Milestone 2 logic currently lives under `src/` rather than shared package boundaries.

## Risks and watchouts

- Milestone 2 logic exists in `src/` and in a separate backoffice parser flow; without consolidation, business rules could diverge over time.
- The backoffice import reads generated JSON output, so stale artifacts can misrepresent the latest logic if sync is not rerun.
- Mixed implementation surfaces (static `src/` assets and Next.js apps) remain a coordination risk until a single source-of-truth architecture is chosen.

## Next practical steps

1. Decide whether Milestone 2 business logic should stay in `src/` or move to a reusable shared package for both static and Next.js surfaces.
2. Add a small verification script that checks `uis/backoffice` can load `.trackflow-milestone2-output.json` before submission.
3. Keep memory-bank entries updated when milestone outputs or UI integration paths change.
