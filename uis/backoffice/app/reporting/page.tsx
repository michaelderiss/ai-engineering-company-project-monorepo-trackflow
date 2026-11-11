"use client";

import { useCallback, useEffect, useState } from "react";
import { RequestError } from "../../../../packages/shared/http";
import {
  getLatestPipelineRun,
  getWeeklyWarehouseClientPerformance,
  PipelineRun,
  WeeklyWarehouseClientPerformance,
} from "../../lib/reporting";

function displayDate(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function displayError(error: unknown): string {
  if (error instanceof RequestError && error.status === 404) {
    return "No weekly report has been computed yet.";
  }
  return "Could not load the warehouse performance report. Please retry.";
}

export default function ReportingPage() {
  const [report, setReport] = useState<WeeklyWarehouseClientPerformance | null>(null);
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runError, setRunError] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    const [reportResult, runResult] = await Promise.allSettled([
      getWeeklyWarehouseClientPerformance(),
      getLatestPipelineRun(),
    ]);
    if (reportResult.status === "fulfilled") setReport(reportResult.value);
    else {
      setReport(null);
      setError(displayError(reportResult.reason));
    }
    if (runResult.status === "fulfilled") {
      setRun(runResult.value);
      setRunError("");
    } else {
      setRun(null);
      setRunError("Pipeline run status is not available.");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, revision]);

  async function triggerRun() {
    if (triggering) return;
    setTriggering(true);
    setRunError("");
    try {
      await import("../../lib/reporting").then(({ triggerPipelineRun }) => triggerPipelineRun());
      setRunError("Pipeline run queued. Refresh shortly to see its status.");
    } catch {
      setRunError("Could not start the pipeline. Please try again or contact TrackFlow Tech.");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <main className="warehouse-reporting">
      <header className="panel-header">
        <div>
          <p className="reporting-eyebrow">Warehouse Operations</p>
          <h1>Weekly Warehouse &amp; Client Performance</h1>
          <p>For Thomas and Ana: one weekly view of inbound volume, orders dispatched, stockout activity, and inventory accuracy.</p>
        </div>
        <a className="text-link" href="/">Operations Home</a>
      </header>

      <section className="panel reporting-run-panel" aria-labelledby="run-heading">
        <div>
          <h2 id="run-heading">Latest pipeline run</h2>
          {run ? (
            <p>
              <strong>{run.status}</strong> · Week: {run.week_start ?? "not specified"} ·
              {" "}Started: {displayDate(run.start_time)} ·
              {" "}Finished: {displayDate(run.end_time)} ·
              {" "}{run.records_processed} events processed
            </p>
          ) : <p>{runError || "No pipeline run has been recorded."}</p>}
        </div>
        <div className="reporting-actions">
          <button type="button" disabled={triggering} onClick={() => void triggerRun()}>
            {triggering ? "Starting..." : "Run report now"}
          </button>
          <button type="button" className="reporting-secondary-button" onClick={() => setRevision((value) => value + 1)}>
            Refresh
          </button>
        </div>
      </section>
      {runError && <p role="status" className="reporting-feedback">{runError}</p>}

      <section className="reporting-results" aria-labelledby="results-heading">
        <h2 id="results-heading">
          Weekly results{report ? ` · Week starting ${report.week_start}` : ""}
        </h2>
        {loading && <p role="status">Loading weekly results...</p>}
        {!loading && error && (
          <p role="alert" className="error">{error} <button type="button" onClick={() => setRevision((value) => value + 1)}>Retry</button></p>
        )}
        {!loading && !error && report && report.entries.length === 0 && (
          <p>No warehouse or client activity is recorded for the week starting {report.week_start}.</p>
        )}
        {!loading && !error && report && report.entries.length > 0 && (
          <div className="reporting-table-scroll">
            <table className="reporting-table">
              <caption className="sr-only">Weekly business performance by warehouse and client for week starting {report.week_start}</caption>
              <thead>
                <tr>
                  <th scope="col">Warehouse</th>
                  <th scope="col">Client</th>
                  <th scope="col">Inbound Volume<br /><small>units received</small></th>
                  <th scope="col">Outbound Throughput<br /><small>orders dispatched</small></th>
                  <th scope="col">Stockout Frequency<br /><small>events</small></th>
                  <th scope="col">Discrepancy Rate<br /><small>events / orders</small></th>
                </tr>
              </thead>
              <tbody>
                {report.entries.map((entry) => (
                  <tr key={`${entry.warehouse}:${entry.client_id}`}>
                    <td>{entry.warehouse === "los_angeles" ? "Los Angeles" : "Zaragoza"}</td>
                    <td>{entry.client_id}</td>
                    <td>{entry.inbound_units_count.toLocaleString()}</td>
                    <td>{entry.outbound_orders_count.toLocaleString()}</td>
                    <td>{entry.stockout_events_count.toLocaleString()}</td>
                    <td>
                      {(entry.discrepancy_rate * 100).toFixed(2)}%
                      <span className="reporting-subvalue">{entry.discrepancy_events_count} discrepancy events</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
