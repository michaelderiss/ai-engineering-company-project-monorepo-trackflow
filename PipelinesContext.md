# BRIEFING — TrackFlow (Business Performance Pipeline)

## Data Pipeline Projects (Design · Implementation · Subflows & Tests)

<!-- hide -->

_Estas instrucciones están [disponibles en español](./trackflow-pipeline-BRIEFING.es.md)._

<!-- endhide -->

This file is self-contained: it gives you everything you need to scope, build, and test the business performance pipeline for TrackFlow, without having to go hunting through other documents. It builds directly on the mandatory metrics already defined in your `trackflow-BRIEFING.md` (telemetry) — read that first if you haven't.

---

## 1. The business deliverable

Thomas (CEO) wants a **weekly report** he can open without calling Ana or Miguel, comparing how each warehouse is performing per client — the thing his directors currently spend hours assembling by hand every Sunday night.

> **Target deliverable:** a weekly, per-warehouse, per-client rollup of throughput, stockout activity, and inventory accuracy — the "Weekly Warehouse & Client Performance Report."

This is the **one concrete deliverable** your pipeline exists to produce. Everything in your `PIPELINE_DESIGN.md` should trace back to it.

**Audience:** Thomas (CEO) and Ana (Head of Warehouse Operations) — non-technical stakeholders who need numbers, not raw events.
**Cadence:** weekly (fresh as of Monday morning, matching the existing "automated weekly executive report" expectation leadership already has).

---

## 2. KPIs to Measure

**These are the KPIs this pipeline exists to produce.** Everything else in this document — source events, aggregation logic, table schema — is implementation detail in service of these four numbers. If you're unsure what to build next, come back to this list.

| KPI                        | What it measures                                                                                     | Why it matters to TrackFlow                                                                              |
| ------------------------------ | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------|
| **Inbound Volume**           | How many units of a client's goods a warehouse received during the week.                                | Shows incoming workload per warehouse and client — the basis for capacity planning (Ana).                    |
| **Outbound Throughput**      | How many orders a warehouse picked and dispatched for a client during the week.                          | The processing-capacity signal — how much a warehouse is actually able to move, not just receive.            |
| **Stockout Frequency**       | How many times during the week a client's SKU at a warehouse fell below the configured minimum.          | An early warning before a client-facing stockout occurs — Miguel needs this to manage client expectations.    |
| **Discrepancy Rate**         | The share of the week's outbound orders associated with a detected inventory discrepancy.                | The inventory-accuracy signal — flags which warehouse/client combinations need an audit.                     |

Everything below this point exists only to compute these four numbers correctly, reliably, and auditable.

---

## 3. Source data

Your source is `telemetry_events`, filtered to the mandatory metrics already defined in your telemetry BRIEFING:

| `event_type`                     | Feeds which KPI(s)                       |
| ------------------------------------ | ---------------------------------------------- |
| `inbound_order_created`            | Inbound Volume                                  |
| `outbound_order_created`           | Outbound Throughput, Discrepancy Rate (denominator) |
| `stock_threshold_triggered`        | Stockout Frequency                              |
| `inventory_discrepancy_detected`   | Discrepancy Rate (numerator)                    |

You don't need any event outside this list for v1 — resist the urge to widen scope.

---

## 4. Required aggregation

- **Grain:** one row per `warehouse` per `client_id` per ISO week (`week_start` = the Monday of that week, UTC).
- **Dimensions:** `warehouse` (`los_angeles`/`zaragoza`), `client_id`, `week_start`.
- **Computed fields per row (each maps directly to a KPI from section 2):**
  - `inbound_units_count` — Inbound Volume: sum of quantities from `inbound_order_created` for the week
  - `outbound_orders_count` — Outbound Throughput: count of `outbound_order_created` for the week
  - `stockout_events_count` — Stockout Frequency: count of `stock_threshold_triggered` for the week
  - `discrepancy_events_count` — supporting count of `inventory_discrepancy_detected` for the week
  - `discrepancy_rate` — Discrepancy Rate: `discrepancy_events_count / outbound_orders_count` (0 if no orders that week)

There is no currency dimension here — this deliverable is operational (volume and accuracy), not cost-based.

---

## 5. Destination table

Create this table under a dedicated `reporting` schema — never write into `telemetry_events`:

```sql
create table reporting.weekly_warehouse_client_performance (
  id uuid primary key default gen_random_uuid(),
  warehouse text not null,
  client_id text not null,
  week_start date not null,
  inbound_units_count integer not null default 0,
  outbound_orders_count integer not null default 0,
  stockout_events_count integer not null default 0,
  discrepancy_events_count integer not null default 0,
  discrepancy_rate numeric not null default 0,
  computed_at timestamptz not null default now(),
  unique (warehouse, client_id, week_start)
);
```

The `unique (warehouse, client_id, week_start)` constraint is what your idempotency strategy (upsert) should rely on.

---

## 6. New reporting endpoint

Expose this pipeline's output through a **new** module, `services/reporting/`, separate from `services/telemetry/`:

- `GET /reporting/weekly-warehouse-client-performance` — accepts optional `week_start` (defaults to the most recent computed week); returns all warehouse/client combinations for that week:

```json
{
  "week_start": "2026-07-13",
  "entries": [
    {
      "warehouse": "los_angeles",
      "client_id": "fashion-co",
      "inbound_units_count": 4200,
      "outbound_orders_count": 980,
      "stockout_events_count": 3,
      "discrepancy_events_count": 2,
      "discrepancy_rate": 0.002
    }
  ]
}
```

- `GET /reporting/pipeline-runs/latest` — status and metadata of the last pipeline run (this can be the same pattern you'll reuse for any future pipeline).
- `POST /reporting/pipeline-runs` — triggers a manual run.

---

## 7. Business constraints

- Each row belongs to a single client — never aggregate across clients within the same row.
- This pipeline reads `telemetry_events` **read-only**. It never writes back to it.
- `services/telemetry/analysis.py` and `GET /telemetry/report` are out of scope for this milestone — do not modify them.

## Part 1

Your challenge
You are building on your own fork of the company's monorepo selected at the beginning of the course - not on a new repository.
Over the past weeks you captured telemetry events, stored them in telemetry_events, and built a technical report - event volume, error rates, latency- for your own engineering team. That technical reporting path stays as it is. Do not change services/telemetry/analysis.py or the GET /telemetry/report endpoint, and do not use telemetry_events as this pipeline's destination. If your data-pipelines company-BRIEFING.md requires an additive payload field on an existing mandatory event type (for example a cost field), add that field to the capture schema - that is an extension of telemetry, not a rewrite of the technical report.
Today your tech lead is asking for something different: a new data pipeline, designed from scratch, whose only job is to turn that same telemetry into data that describes how the business is performing - the kind of numbers a department head or the CEO would read, not the kind an engineer uses to debug a service.
Technical Brief- Business Performance Data Pipeline (Design Phase)
Before writing a single line of orchestration code, I need you to document the design of a new data pipeline. This one isn't for us - it's for the business side: the leadership team that's been asking for a real report instead of a PDF someone assembles by hand on your company's BRIEFING cadence. This is a new pipeline, built on top of the telemetry you already have. Your technical report and the GET /telemetry/report endpoint keep serving engineering exactly as before. telemetry_events remains the source (never this pipeline's destination). Additive payload fields required by your data- pipelines BRIEFING on existing event types are allowed. What you're building now reads from that source but produces a different kind of output: numbers a non-technical stakeholder can act on.
Deliverable: a design document in Markdown, committed to the monorepo. No orchestration code yet - design first, implementation next.
What makes a data pipeline robust?
A data pipeline is not simply a script that moves data from one place to another. A production pipeline has well-defined stages, handles failures predictably. and can be audited. The three key attributes that separate a robust pipeline from one that "just works" are:
• Idempotency: running the pipeline twice on the same data produces the same result - no duplicates, no corruption.
• Observability: every run leaves enough traces to know what happened, when, and why.
• Recoverability: when the pipeline fails mid-way, the next run knows exactly where to resume.
These three attributes are what your design document must demonstrate you have thought through deeply.
Build this pipeline around a real business need
A data pipeline is not infrastructure for its own sake - even less so this one. Its only reason to exist is a business question that your company-BRIEFING.md already scopes for you, but that nobody is answering reliably today.
Before you design extraction, transformation, or load stages, read your company-BRIEFING.md from the data pipelines context-it names the one concrete business deliverable your company needs, who it's for, at what cadence, the exact KPIs it must compute (see its "KPIs to Measure" section), and which mandatory metrics feed them. (This is the follow-through on what your telemetry company-BRIEFING.md flagged back in section 4, "How These Metrics Connect to the Future" - this is that moment, now spelled out concretely.)
Design the pipeline to produce exactly the data that deliverable needs - at the right freshness, granularity, and audit trail. Don't invent a generic KPI; the one your company needs is already scoped for you in company-BRIEFING.md.
This is a new pipeline, not a replacement. The technical telemetry report you built earlier keeps answering technical questions for engineers (volume, errors, latency). This pipeline answers a different question, for a different audience, and its output lives in different tables and different endpoints. Do not change the technical report path (services/telemetry/analysis.py. GET /telemetry/report) or use telemetry_events as this pipeline's destination - additive required-BRIEFING payload fields on existing event types are the only allowed telemetry schema extension.
When you write the pipeline purpose in Phase 2, name the business deliverable you're targeting and the mandatory metric(s) that feed it. If a stage in your design doesn't support that deliverable, question whether it belongs in v1.
How to Start
1. Run git pull on your monorepo fork to make sure you have the latest state.
2. Explore the data/folder in the monorepo - it contains the subfolders raw/ process/
pipelines/.and eval/ that you will use throughout this
module. Orchestration code will live in data/pipelines/: reusable transformation scripts in data/process/: HTTP endpoints that query or trigger the pipeline will live in services/ and import from data/pipelines/ - not the other way around.
3. Create the file data/pipelines/PIPELINE_DESIGN.md - that is where your design document goes.
4. Read your company-BRIEFING.md from the data pipelines context - its "KPIs to Measure" section names the exact numbers this pipeline must produce, and it also states the audience, cadence, required aggregation, and destination table. (The mandatory metrics feeding those KPIs are the ones from your telemetry company-BRIEFING.md, already familiar from the earlier milestone.)
5. This pipeline's output does not belong in telemetry_events. All new destination tables live under a dedicated reporting schema. Use the table exactly as named in your company-BRIEFING.md Destination table section (not a generic reporting.business_metrics) - and expose it through a new services/reporting/ module, kept separate from services/telemetry/ and the GET /telemetry/report endpoint.
Note on tooling: Today you are introduced to Prefect as an orchestration framework-flows, tasks, states, and configuration blocks. Your design document should reflect how you would organize your pipeline using these concepts, even though the code implementation comes over the next days.
What You Need to Do
Phase 1 - Current state analysis
Document in a "Current State" section what you already have: the telemetry events captured so far, where they're stored, and what your existing technical report already answers for engineering.
Identify the gap: which business question from your company-BRIEFING.md is still unanswered by that technical report, and would require a dedicated pipeline?
Phase 2 - Pipeline design
Define the purpose of the pipeline in a single concrete sentence: name the specific business deliverable you're targeting (e.g., "produce the rollup that feeds [role]'s executive report at the BRIEFING cadence"), the KPI(s) it computes (from your company-BRIEFING.md's "KPIs to Measure" section), and the mandatory metric(s) from your telemetry BRIEFING it's built on.
Specify the extraction format: your source is telemetry_events (plus any other existing domain tables you need) - in what format the data arrives, and how often it's updated.
Design the data flow with a text or Mermaid diagram showing at least three clearly separated stages: extraction, transformation, and load.
Describe how you would handle a source that updates existing records rather than always inserting new ones - explain the concrete strategy to avoid duplicates in your specific case.
Name the new destination table(s) under the reporting schema using the exact name from your company-BRIEFING.md Destination table section, and the new endpoint(s) in services/reporting/ that will expose it (status, manual trigger, and KPI query) - explicitly separate from telemetry_events and GET /telemetry/report

Phase 3 - Resilience and idempotency
Define your idempotency strategy: if the pipeline fails during the load phase and is re-run, explain exactly how you guarantee that already-loaded data is neither corrupted nor duplicated.
Design your execution log: specify the minimum fields you would record in every run (start time, end time, records processed, status, errors) and explain why each field is necessary to audit the pipeline in production.
Phase 4 - Mapping to Prefect
Map your design to Prefect concepts: identify at least one main flow and at least three tasks (extract, transform, load as a minimum), plus which states (Running. Completed, Failed) are relevant. A second flow (e.g. backfill) is optional in Part 1 - Part 3 will raise the bar by splitting stages into subflows.
Indicate which configuration or credentials you would manage as Prefect blocks (for example, the connection to Supabase).
Phase 5 - Application integration (design only)
Sketch the three new endpoints in services/reporting/ the business side will use: status query, manual trigger, and KPI query (the feed Part 3's dashboard will consume) -kept separate from services/telemetry/ and the GET /telemetry/report endpoint.
For each endpoint, state which function or flow in data/pipelines/ it will call - no ETL logic belongs in services/
A IMPORTANT: Field names, entity IDs, and domain-specific values in your design must match your company's domain vocabulary in the monorepo. A generic design that ignores your company's data model will not be accepted.
? Questions to Help You Design the Pipeline
Before writing PIPELINE_DESIGN.md. answer in writing - even as a draft - how you would handle each case in your monorepo.
Idempotency
1. Duplicates at the source - How do you prevent counting the same action twice in telemetry_events and your business aggregates? Which envelope field is your dedup key, and at which layer?
► See example and hint
2. Re-run after failure - If the pipeline dies during load with partial data inserted, what happens when you re-run it? How do you guarantee the same outcome as a clean run?
►See example and hint
3. Late events - How do you recompute a published daily business metric when a delayed event arrives, without inflating numbers or losing audit trail? ►See example and hint
Observability
1. Silence vs. true absence - How do you tell zero activity from failed capture or a pipeline that never ran? What minimum signals would you record? ►See example and hint
2. Collection traceability - What traces reconstruct the path event→ business report and detect gaps, bursts, or interval drift?
► See example and hint
3. Growth vs. data loss - If event volume swings day to day, how do you know the business is growing vs. losing or duplicating measurements? ►See example and hint
Recoverability
1. Database outage - Where do you resume if the connection drops mid-pipeline? What checkpoint do you persist?
►See example and hint
2. Frontend buffer - Does buffering offline events in the browser make sense? What risks does it introduce, and which layer should own them?
► See example and hint
3. Transmission retry - How do you design retries on POST /telemetry without breaking idempotency? What server response means "already stored" vs. "retry"?
► See example and hint
Cross-cutting
1. Concurrent runs - What do you observe, how do you avoid load race conditions, and how do you recover when cron and a manual trigger from services/ overlap?
See example and hint
What We Will Evaluate
The file data/pipelines/PIPELINE_DESIGN.md exists in the monorepo and is written in readable Markdown.
PIPELINE_DESIGN.md has a Current State section plus the business gap (what the telemetry report does vs does not answer).
Extraction format is specified (source tables, payload shape, update cadence).
The pipeline purpose is defined in a single concrete sentence that names the business deliverable and KPI(s) from the company's company-BRIEFING.md - not a generic or technical KPI.
The design does not modify services/telemetry/analysis.py or GET /telemetry/report, and does not write this pipeline's output into telemetry_events - output lives in new tables under a reporting schema and is exposed through a new services/reporting/module. Additive required-BRIEFING payload fields on existing event types are allowed.
The data flow diagram shows at least three distinct stages (extraction, transformation, load) with the real entity or table names from the company. The strategy for handling updates to existing records is documented with a concrete mechanism (e.g., upsert by primary key, last-modified timestamp, control table).
The idempotency strategy is explicit: it describes what happens on the second run after a load-phase failure, not just what would be desirable.
The execution log specifies at least five fields with the field name, data type, and justification for why that field is necessary for auditing.
The Prefect mapping identifies at least one main flow and three tasks with concrete names aligned with the pipeline stages (matches Part 2's implementation bar; Part 3 adds subflows).
The design documents at least three planned services/reporting/ endpoints (status query, manual trigger, and KPI query for the dashboard) and names the data/pipelines/functions each will import.
The design is consistent with the telemetry events and mandatory metrics already defined in the company's BRIEFING file.
How to Submit
1. Make sure data/pipelines/PIPELINE_DESIGN.md is committed to your monorepo fork.
2. Commit with the message: feat: add business performance pipeline design document.
3. Push your changes to your GitHub repository and share the URL with your tech lead.
## Part 2

Milestone - Implementing a Resilient Business Performance Pipeline (Part 2 of 3)
Before you start: Keep your company-BRIEFING.md open while you code - it is the source of truth for KPI names, destination table schema, and the endpoint contract you implement. Also have your approved data/pipelines/PIPELINE_DESIGN.nd from Part 1 ready.
Your challenge
You are building on your own fork of the company's monorepo selected at the beginning of the course - not on a new repository.
The design document is approved. Now it's time to build it - a pipeline that reads from telemetry_events and produces the business-facing KPIs you scoped in Part 1, exactly as named in your company-BRIEFING.md. Your existing technical telemetry system (telemetry_events services/telemetry/analysis.py. GET /telemetry/report) is not part of this work - it stays untouched, still serving engineering.
There is a fundamental difference between a script that works on your machine and a pipeline that can run in production unattended: resilience.
Implementation Ticket - Resilient Business Performance Pipeline
The design is approved. Leadership wants to see this pipeline running, not just documented. Non-negotiable requirements before handoff to production: - The pipeline must tolerate partial failures without interrupting the entire execution. - Tasks that touch external services must have retries configured.- The pipeline must be runnable as a script from the command line. - If a task has already run successfully in the last hour, it must not repeat unnecessarily. Starting point: your data/pipelines/PIPELINE_DESIGN.md from the previous day. Implement what you designed - reading from telemetry, writing to the new business reporting table you scoped, nothing about the existing technical report changes.
What makes a pipeline resilient?
A resilient pipeline is not one that never fails - it is one that fails well. In Prefect, that means three concrete things:
• Partial failure tolerance: a failing task does not bring down the entire flow. Prefect distinguishes between critical tasks (whose failure should stop everything) and optional tasks (whose failure should be logged and allow the flow to continue).
• Smart retries: tasks that interact with external services (databases, APIs) are configured with retries and retry_delay_seconds to absorb transient failures without human intervention.
• Result caching: if a task already produced a valid result recently, Prefect can reuse it rather than repeating the computation. This is especially useful for expensive transformations.
How to Start
1. Run git pull on your monorepo fork to make sure you have the latest state.
2. Open your data/pipelines/PIPELINE_DESIGN.md - that document is your specification. Implement what you designed.
3. Keep your company-BRIEFING.md from the data pipelines context open while you code: it's the source of truth for the exact KPI names (its "KPIs to Measure" section), the destination table schema, and the endpoint contract you're implementing. (The event fields you're extracting from are the ones your telemetry company-BRIEFING.md already defined as mandatory.)
4. Write your pipeline code in data/pipelines/. The main entry point must be named data/pipelines/pipeline.py. Use data/raw/ for input data and intermediate files, data/process/ for reusable transformation scripts, and data/eval/ for pipeline validation outputs.
5. The extraction task reads from telemetry_events (and any other domain tables you need) -- read-only. The load task writes to the new destination table named in your company-BRIEFING.md (under the reporting schema) that you designed in Part 1. Do not write back into telemetry_events and do not modify services/telemetry/analysis.py.
6. Any endpoint that exposes or triggers the pipeline (for example, to query the status of the last run or launch a run manually) must be implemented in services/reporting/, a module separate from services/telemetry/. importing functions and flows from data/pipelines/ as needed.
7. Install Prefect 3 in your environment: uv add "prefect>=3"
What You Need to Do
Phase 1 - Flows and tasks
Implement the pipeline as one or more Prefect flows (@flow) following the stage structure from your design: extraction, transformation, and load as a minimum.
Each stage must be an independent task (@task) with explicit inputs and outputs.
Include at least one optional/non-critical step (for example, a notification, secondary export, or eval snapshot) and invoke it with return_state=True so that a failure in that step does not interrupt the main extract-transform load execution.
Phase 2 - Resilience
Add retries and retry_delay_seconds to every task that interacts with external services (database, APIs). Justify the number of retries chosen in a
comment.
Handle at least one task failure explicitly in the flow using return_state=True rather than letting it propagate automatically.
Add caching (cache_key_fn.cache_expiration) to at least one expensive transformation task. Explain in a comment what defines the cache key and how long it is valid.
Phase 3 - Idempotency
The load phase must be idempotent: if the pipeline runs twice over the same data range, the result in your BRIEFING destination table must be identical after both runs. Implement the strategy you documented in your design (upsert, control table, timestamp, or another) - the unique constraint from your company- BRIEFING.md schema is what your upsert should key off.
Record in the database or in a log file the minimum execution metadata for each run: start time, end time, records processed, final status, and any captured errors. Phase 4 - Script-based execution
Ensure data/pipelines/pipeline.py can be executed directly as a CLI script (for example, with an if _name_ main flow).
__main_
block that invokes the
Verify the full pipeline runs without errors: python data/pipelines/pipeline.py
Document the intended schedule for your company's reporting cycle in data/pipelines/PIPELINE_DESIGN.md and the run command in a comment or the same design doc.
Phase 5 - Backend endpoints
In services/reporting/. implement three endpoints related to this pipeline: (1) query the status and metadata of the last run, (2) trigger a manual flow run, (3) query the KPI rows from the BRIEFING destination table - this is what the Part 3 dashboard will consume. Keep them in their own module, separate from services/telemetry/
The endpoints must import flows or functions from data/pipelines/ - do not duplicate pipeline logic in services/
The endpoints follow the same authentication conventions and response structure as the rest of your API, and the KPI query endpoint's response shape matches the contract in your company-BRIEFING.md
AIMPORTANT: Flow names, task names, table names, and field names must match what is defined in data/pipelines/PIPELINE_DESIGN.md and your company-BRIEFING.md from the data pipelines context (KPIs and schema) - consistent, in turn, with the event fields already defined in your telemetry company-BRIEFING.md. A generic implementation that ignores your company's data model will not be accepted.

What We Will Evaluate
The file data/pipelines/pipeline.py exists and defines at least one flow with three or more tasks.
At least one task has retries configured with a value greater than zero and a comment justifying the number chosen.
At least one optional task is invoked with return_state=True and the flow continues executing when that task fails.
At least one transformation task has caching configured with cache_key_fn and cache_expiration
The load phase is idempotent: running the pipeline twice over the same data does not produce duplicates in the BRIEFING destination table.
Each pipeline run records at least five metadata fields (start time, end time, records processed, status, errors) in the database or in a structured log file. python data/pipelines/pipeline.py runs the full ETL flow without errors.
The run command is documented in data/pipelines/PIPELINE_DESIGN.md or inline comments.
The pipeline writes to the destination table defined in your company-BRIEFING.md Destination table section - telemetry_events and services/telemetry/analysis.py are untouched.
At least one endpoint exists in services/reporting/ that returns the metadata of the last pipeline run (status, start time, end time, records processed). At least one endpoint exists in services/reporting/ that triggers a manual flow run, importing the function from data/pipelines/without duplicating the logic.
At least one endpoint exists in services/reporting/ that returns the KPI rows from the BRIEFING destination table (the contract the Part 3 dashboard will consume).
The KPI values produced match the definitions in your company-BRIEFING.md's "KPIs to Measure" section - not a reinterpretation of them.
The implemented design is consistent with data/pipelines/PIPELINE_DESIGN.md - the stages, entities, and resilience strategies described there are reflected in the code.
How to Submit
1. Make sure data/pipelines/pipeline.py.the endpoints in services/reporting/, and any supporting files are committed to your monorepo fork. 2. Commit with the message: feat: implement resilient business performance pipeline
3. Push your changes to your GitHub repository and share the URL with your tech lead.
## Part 3

Milestone - Pipeline Enhancement: Subflows and Tests (Part 3 of 3)
Before you start: Make sure you have completed Part 2 of this Milestone - this project builds directly on data/pipelines/pipeline.py implemented in the previous session. Keep your company-BRIEFING.md open - KPI names, schema, and stakeholder audience come from there.
Your challenge
You are building on your own fork of the company's monorepo selected at the beginning of the course - not on a new repository.
This is Part 3 of this Milestone - Telemetry and Data Pipelines. Your business performance pipeline already works: it reads from telemetry_events and produces the KPIs leadership asked for - the ones named in your company-BRIEFING.md - without touching the existing technical telemetry system. Today you bring it to production level: you refactor the main flow into reusable subflows, add unit tests that validate the behaviour of transformation tasks, ensure the pipeline runs directly from the command line, and - this is the part leadership actually cares about - put those KPIs in front of a dashboard someone can read.
Enhancement Ticket - Pipeline to Production
The basic pipeline is ready. Before the final handoff to the operations team, I need four more things:
1. The main flow is growing - refactor it into subflows so that each phase is independent, testable, and reusable.
2. I need unit tests for the transformation tasks. If a test fails, I want to know before the pipeline reaches production, not after.
3. After the subflow refactor, the pipeline must still be runnable as a script: python data/pipelines/pipeline.py completes without errors (keep the Part 2 entrypoint).
4. I need a dashboard. Nobody on the leadership team is going to query an endpoint - put the KPIs somewhere they can actually look at them. Starting point: data/pipelines/pipeline.py from the previous session.
Why subflows
Parts 1-2 required one main flow with at least three tasks. This part raises that bar: you split those stages into at least three subflows (@flow) coordinated by the main flow - that topology is new to Part 3 and is what we evaluate here.
A flow that grows without structure ends up being as hard to maintain as the script it replaced. Subflows apply the DRY principle at the orchestration level: each phase of the pipeline (extraction, transformation, load) becomes an independent flow that can be executed, monitored, and reused separately. The main flow coordinates them but does not contain their logic.
| PR approved → merge it into main . Otherwise the feature never gets deployed, and your next branch starts from outdated code, which leads to merge conflicts.
How to Start
1. Run git pull on your monorepo fork.
2. Open data/pipelines/pipeline.py - that is your starting point.
3. Keep your company-BRIEFING.md at hand: subflow, task, and test names should reflect the KPI names from its "KPIs to Measure" section and the schema you implemented - not generic labels.
4. Keep the existing folder structure: data/pipelines/ for flows and subflows, data/process/ for transformation logic, data/raw/ for input data, data/eval/ for validation outputs.
5. Unit tests go in tests/pipelines/ at the root of the monorepo.
6. The dashboard page goes in uis/backoffice/. fetching from the KPI query services/reporting/ endpoint you built in Part 2.
7. Ensure Prefect 3 is installed from Part 2: uv add "prefect>=3"
What You Need to Do
Phase 1 - Refactoring into subflows
Split the main flow into at least three subflows (@flow) that correspond to the stages from your design: one for extraction (from telemetry_events and any other domain tables), one for transformation, and one for load (into the destination table named in your company-BRIEFING.md). The main flow invokes them in sequence.
Each subflow must have explicit inputs and outputs - do not rely on global variables between subflows.
If you have optional steps (notifications, secondary exports), extract them as subflows too and invoke them with return_state=True from the main flow. Phase 2 - Unit tests
Create the file tests/pipelines/test_pipeline.py with unit tests for at least three transformation tasks - the ones that compute the KPIs from your company-BRIEFING.md
Each test must verify the task's behaviour in isolation: it must not depend on a database or external APIs. Use in-memory test data shaped like your telemetry events (per your company-BRIEFING.md
Include at least one test that verifies the defensive behaviour of a task against invalid or malformed input (for example, a null field where none is expected, or an incorrect type).
Include at least one test that asserts a computed KPI value matches the definition in your company-BRIEFING.md for a known, hand-calculated input. The tests must pass with python -m pytest tests/pipelines/test_pipeline.py without errors.
Phase 3 - CLI still works after the refactor
After the subflow split, python data/pipelines/pipeline.py still runs the full ETL without errors (the Part 2 must keep working - do not rebuild them from scratch).
main
entrypoint and run-command docs from
Phase 4 - Business dashboard (mandatory)
Your pipeline produces KPIs - but a table nobody looks at isn't a deliverable. This phase is not optional: leadership needs to actually see the numbers, not query an endpoint with curl.
Build a page in uis/backoffice/ (eg. /reporting) that fetches your services/reporting/ endpoint and renders every KPI from your company- BRIEFING.md 's "KPIs to Measure" section - a chart or a table per KPI is enough.
Label each KPI clearly with the same name it has in your company-BRIEFING.md, and show the period (week or month, per your cadence) the data covers. This dashboard is business-facing, not a developer tool: it should be legible to the stakeholder named in your company-BRIEFING.md (e.g. the CEO or department head) without needing anything translated or explained.
No need for visual polish - a working, correctly labeled view of real data from your BRIEFING destination table is the goal.
▲ IMPORTANT: Subflow names, task names, and test names must follow the same domain vocabulary defined in data/pipelines/PIPELINE_DESIGN.md and your company-BRIEFING.md. A subflow named extract_data is not acceptable if your company has concrete entities and KPI names - name it after the actual business metric this pipeline produces.

Additional Activity - Extra Enhancements from Your Design Questions
Go back to the "Questions to Help You Design the Pipeline" section from Part 1. If, while answering those questions, you identified resilience or observability enhancements beyond what Phases 1-3 already cover (for example, a heartbeat plus silence alert, a concurrency lock for overlapping runs, or an Idempotency- Key pattern for retries) and haven't implemented them yet, this is the place to do it.
For each enhancement you add, note in data/pipelines/PIPELINE_DESIGN.md which question it answers and why you prioritized it.
This is optional - only pick it up if your own design doc actually flagged something worth building. Don't invent an enhancement just to check a box.
What We Will Evaluate
The main flow in data/pipelines/pipeline.py invokes at least three subflows (@flow) instead of containing all logic directly.
Each subflow has explicit inputs and outputs and can be executed independently.
The file tests/pipelines/test_pipeline.py exists and contains at least three unit tests for transformation tasks.
Unit tests run in isolation: in-memory fixtures shaped like BRIEFING telemetry - no live database or external APIs.
At least one test verifies the defensive behaviour of a task against invalid input.
At least one test validates a KPI's computed value against its definition in company-BRIEFING.md
python -m pytest tests/pipelines/test_pipeline.py passes without errors.
After the subflow refactor, python data/pipelines/pipeline.py still runs the full ETL flow without errors (Part 2 CLI entrypoint preserved).
Subflow names, task names, and test names reflect the domain vocabulary and KPI names from company-BRIEFING.md
telemetry_events and services/telemetry/analysis.py remain unmodified throughout the refactor.
A dashboard exists in uis/backoffice/ that displays every KPI from company-BRIEFING.md's "KPIs to Measure" section, correctly labeled, sourced from your services/reporting/ endpoint.
The dashboard is legible to a non-technical business stakeholder, not just to another engineer.
How to Submit
1. Make sure data/pipelines/pipeline.py.tests/pipelines/test_pipeline.py, and the dashboard page in uis/backoffice/ are committed to your monorepo fork.
2. Commit with the message: feat: refactor business performance pipeline into subflows, add unit tests, and add reporting dashboard
3. Open a Pull Request with these changes - it can build on the Part 2 PR or be a new one. In the PR description, mention whether you implemented any additional enhancement from the design questions, and which one. Share the URL with your tech lead.