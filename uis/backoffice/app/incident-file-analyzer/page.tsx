"use client";

import { FormEvent, useState } from "react";
import dynamic from "next/dynamic";
import { apiFetch, apiResponse, isObject } from "../../lib/auth";
import type { AnalysisResult } from "../../components/IncidentAnalysisReport";

const IncidentAnalysisReport = dynamic(() => import("../../components/IncidentAnalysisReport"), {
  ssr: false,
  loading: () => <p role="status">Loading analysis report...</p>,
});

function validAnalysis(value: unknown): boolean {
  return isObject(value) && ["total_records", "valid_records", "invalid_records", "satisfaction_average", "scored_closed_incidents", "closed_incidents"].every((field) => typeof value[field] === "number") && ["invalid_breakdown", "category_breakdown", "status_breakdown", "satisfaction_breakdown"].every((field) => isObject(value[field]) && Object.values(value[field]).every((count) => typeof count === "number"));
}

export default function IncidentFileAnalyzerPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState(false);

  async function onAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Please choose a CSV file before analyzing.");
      return;
    }

    setError(null);
    setLoading(true);
    setExportSuccess(false);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const data = await apiFetch<AnalysisResult>("/api/incidents/analyze", {
        method: "POST",
        body: formData,
      }, validAnalysis);
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unexpected error.";
      setError(message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function onExport(): Promise<void> {
    setExporting(true);
    setExportSuccess(false);
    setError(null);
    let url: string | null = null;
    try {
      const response = await apiResponse("/api/incidents/results/export");
      if (!response.headers.get("content-type")?.includes("text/csv")) throw new Error("Unexpected download format");
      url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "results.csv";
      link.click();
      setExportSuccess(true);
    } catch {
      setError("Could not download the results. Please try Download results CSV again.");
    } finally {
      if (url) URL.revokeObjectURL(url);
      setExporting(false);
    }
  }

  return (
    <main>
      <h1>Incident File Analyzer</h1>
      <p>
        Upload the incidents CSV to validate records, calculate key CX metrics, and
        export one-row-per-metric CSV output.
      </p>

      <section className="panel">
        <form onSubmit={onAnalyze}>
          <label htmlFor="incidentCsv">CSV File</label>
          <br />
          <input
            id="incidentCsv"
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <div className="actions">
            <button type="submit" disabled={loading || exporting}>
              {loading ? "Analyzing..." : "Analyze incidents"}
            </button>
            <button type="button" onClick={() => void onExport()} disabled={!result || loading || exporting}>
              {exporting ? "Downloading..." : "Download results CSV"}
            </button>
            <a href="/" className="launcher-link">
              Back to launcher
            </a>
          </div>
        </form>
        {error && <p className="error">{error}</p>}
        {exportSuccess && <p role="status" className="success">Download started successfully.</p>}
      </section>

      {result && <IncidentAnalysisReport result={result} />}
    </main>
  );
}
