"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getWeeklyPerformance,
  getLatestPipelineRun,
  triggerPipelineRun,
  WeeklyPerformance,
  PipelineRun,
  ReportingEntry,
} from "../../lib/reporting";

const KPI_LABELS: Record<string, string> = {
  inbound_units_count: "Inbound Volume",
  outbound_orders_count: "Outbound Throughput",
  stockout_events_count: "Stockout Frequency",
  discrepancy_events_count: "Discrepancy Count",
  discrepancy_rate: "Discrepancy Rate",
};

function kpiValue(key: string, value: number): string {
  if (key === "discrepancy_rate") {
    return `${(value * 100).toFixed(2)}%`;
  }
  return value.toLocaleString();
}

export default function ReportingDashboardPage() {
  const [performance, setPerformance] = useState<WeeklyPerformance | null>(null);
  const [perfError, setPerfError] = useState("");
  const [perfLoading, setPerfLoading] = useState(true);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const [runError, setRunError] = useState("");
  const [runLoading, setRunLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState("");
  const [triggerError, setTriggerError] = useState("");
  const [perfRevision, setPerfRevision] = useState(0);
  const [runRevision, setRunRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setPerfLoading(true);
    setPerfError("");
    getWeeklyPerformance().then((data) => {
      if (active) setPerformance(data);
    }).catch((_err: unknown) => {
      if (active) setPerfError("Could not load KPI data. The pipeline may not have run yet.");
    }).finally(() => {
      if (active) setPerfLoading(false);
    });
    return () => { active = false; };
  }, [perfRevision]);

  useEffect(() => {
    let active = true;
    setRunLoading(true);
    setRunError("");
    getLatestPipelineRun().then((data) => {
      if (active) setLatestRun(data);
    }).catch((_err: unknown) => {
      if (active) setRunError("Could not load pipeline run status.");
    }).finally(() => {
      if (active) setRunLoading(false);
    });
    return () => { active = false; };
  }, [runRevision]);

  async function handleTrigger() {
    if (triggering) return;
    setTriggering(true);
    setTriggerResult("");
    setTriggerError("");
    try {
      const result = await triggerPipelineRun();
      setTriggerResult(`Pipeline run ${result.run_id} started for week ${result.week_start}.`);
      setPerfRevision((v) => v + 1);
      setRunRevision((v) => v + 1);
    } catch {
      setTriggerError("Failed to trigger pipeline run. Please try again.");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">TrackFlow Backoffice</p>
        <h1>Business Performance Dashboard</h1>
        <p>
          Weekly warehouse and client KPIs computed from telemetry events.
          Data is refreshed nightly; a manual trigger is available below.
        </p>
        <p>
          <Link href="/" className="text-link">
            Back to Backoffice Home
          </Link>
        </p>
      </header>

      <section className="panel">
        <div className="panel-header">
          <h2>Latest Pipeline Run</h2>
          <button disabled={triggering} onClick={handleTrigger}>
            {triggering ? "Triggering\u2026" : "Trigger Pipeline Run"}
          </button>
        </div>
        {triggerResult && <p className="success">{triggerResult}</p>}
        {triggerError && <p className="error">{triggerError}</p>}
        {runLoading && <p>Loading pipeline status\u2026</p>}
        {runError && <p className="error">{runError}</p>}
        {!runLoading && !runError && renderRunStatus(latestRun)}
      </section>

      <section className="panel">
        <h2>Weekly KPIs</h2>
        {perfLoading && <p>Loading KPI data\u2026</p>}
        {perfError && <p className="error">{perfError}</p>}
        {performance && performance.week_start && (
          <>
            <p><strong>Week starting:</strong> {performance.week_start}</p>
            {performance.entries.length === 0
              ? <p>No KPI entries found for this week.</p>
              : performance.entries.map((entry, idx) => renderEntry(entry, idx))}
          </>
        )}
        {performance && !performance.week_start && (
          <p>No reporting data available. Trigger a pipeline run to generate KPIs.</p>
        )}
      </section>
    </main>
  );
}

function renderEntry(entry: ReportingEntry, idx: number) {
  const warehouseLabel = entry.warehouse
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c: string) => c.toUpperCase());
  const clientLabel = entry.client_id
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c: string) => c.toUpperCase());

  return (
    <article key={idx} className="kpi-card">
      <hgroup>
        <h3>{warehouseLabel}</h3>
        <p>{clientLabel}</p>
      </hgroup>
      <div className="grid">
        <div className="metric">
          <h4>{KPI_LABELS.inbound_units_count}</h4>
          <p>{kpiValue("inbound_units_count", entry.inbound_units_count)}</p>
        </div>
        <div className="metric">
          <h4>{KPI_LABELS.outbound_orders_count}</h4>
          <p>{kpiValue("outbound_orders_count", entry.outbound_orders_count)}</p>
        </div>
        <div className="metric">
          <h4>{KPI_LABELS.stockout_events_count}</h4>
          <p>{kpiValue("stockout_events_count", entry.stockout_events_count)}</p>
        </div>
        <div className="metric">
          <h4>{KPI_LABELS.discrepancy_events_count}</h4>
          <p>{kpiValue("discrepancy_events_count", entry.discrepancy_events_count)}</p>
        </div>
        <div className="metric">
          <h4>{KPI_LABELS.discrepancy_rate}</h4>
          <p>{kpiValue("discrepancy_rate", entry.discrepancy_rate)}</p>
        </div>
      </div>
    </article>
  );
}

function renderRunStatus(run: PipelineRun | null) {
  if (!run) {
    return <p>No pipeline runs found yet.</p>;
  }
  const statusClass = run.status === "completed"
    ? "active"
    : run.status === "failed"
      ? "suspended"
      : "";
  return (
    <div className="run-info">
      <p>
        <strong>Status:</strong>{" "}
        <span className={`status-badge ${statusClass}`}>{run.status}</span>
      </p>
      <p><strong>Week:</strong> {run.week_start}</p>
      <p><strong>Started:</strong> {run.started_at}</p>
      {run.completed_at && <p><strong>Completed:</strong> {run.completed_at}</p>}
      {run.records_extracted !== null && (
        <p><strong>Records extracted:</strong> {run.records_extracted.toLocaleString()}</p>
      )}
      {run.records_loaded !== null && (
        <p><strong>Records loaded:</strong> {run.records_loaded.toLocaleString()}</p>
      )}
      <p><strong>Triggered by:</strong> {run.triggered_by}</p>
    </div>
  );
}