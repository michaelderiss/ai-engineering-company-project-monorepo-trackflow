"use client";

import { FormEvent, useMemo, useState } from "react";
import { apiFetch, apiResponse, isObject } from "../../lib/auth";

type AnalysisResult = {
  source_file: string;
  total_records: number;
  valid_records: number;
  invalid_records: number;
  invalid_breakdown: Record<string, number>;
  category_breakdown: Record<string, number>;
  status_breakdown: Record<string, number>;
  country_breakdown: Record<string, number>;
  satisfaction_breakdown: Record<string, number>;
  satisfaction_average: number;
  scored_closed_incidents: number;
  closed_incidents: number;
};

const invalidLabels: Record<string, string> = {
  invalid_country: "Invalid country",
  invalid_carrier: "Carrier/country mismatch",
  invalid_tracking_number: "Invalid tracking number",
  invalid_category: "Invalid or missing category",
  invalid_description: "Invalid or missing description",
  invalid_email: "Invalid or missing email",
  closed_without_score: "Closed incident, no score",
  invalid_score_range: "Satisfaction score out of range",
  invalid_status: "Invalid status",
};

function pct(value: number, total: number): string {
  if (total === 0) {
    return "0.0%";
  }
  return `${((value / total) * 100).toFixed(1)}%`;
}

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

  const invalidRows = useMemo(() => {
    if (!result) return [];
    return Object.entries(result.invalid_breakdown).map(([key, value]) => ({
      key,
      label: invalidLabels[key] ?? key,
      value,
    }));
  }, [result]);

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

      {result && (
        <>
          <section className="panel">
            <h2>General metrics</h2>
            <div className="grid">
              <article className="metric">
                <h4>Total records</h4>
                <p>{result.total_records}</p>
              </article>
              <article className="metric">
                <h4>Valid records</h4>
                <p>{result.valid_records}</p>
              </article>
              <article className="metric">
                <h4>Invalid records</h4>
                <p>{result.invalid_records}</p>
              </article>
              <article className="metric">
                <h4>Average satisfaction</h4>
                <p>{result.satisfaction_average.toFixed(2)} / 5.00</p>
              </article>
            </div>
          </section>

          <section className="panel">
            <h2>Invalid records breakdown</h2>
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {invalidRows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    <td>{row.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>Category breakdown</h2>
            <table>
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Count</th>
                  <th>Percent of valid</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.category_breakdown).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{value}</td>
                    <td>{pct(value, result.valid_records)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>Status breakdown</h2>
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Count</th>
                  <th>Percent of valid</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.status_breakdown).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{value}</td>
                    <td>{pct(value, result.valid_records)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>Satisfaction index</h2>
            <p>
              Scored incidents: {result.scored_closed_incidents} of {result.closed_incidents}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Score</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.satisfaction_breakdown).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </main>
  );
}
