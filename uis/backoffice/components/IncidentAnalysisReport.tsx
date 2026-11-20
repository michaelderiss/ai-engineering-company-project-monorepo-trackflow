"use client";

export type AnalysisResult = {
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

export default function IncidentAnalysisReport({ result }: { result: AnalysisResult }) {
  return (
    <>
      <section className="panel">
        <h2>General metrics</h2>
        <div className="grid">
          <article className="metric"><h4>Total records</h4><p>{result.total_records}</p></article>
          <article className="metric"><h4>Valid records</h4><p>{result.valid_records}</p></article>
          <article className="metric"><h4>Invalid records</h4><p>{result.invalid_records}</p></article>
          <article className="metric"><h4>Average satisfaction</h4><p>{result.satisfaction_average.toFixed(2)} / 5.00</p></article>
        </div>
      </section>
      <section className="panel">
        <h2>Invalid records breakdown</h2>
        <table><thead><tr><th>Rule</th><th>Count</th></tr></thead><tbody>
          {Object.entries(result.invalid_breakdown).map(([key, value]) => <tr key={key}><td>{invalidLabels[key] ?? key}</td><td>{value}</td></tr>)}
        </tbody></table>
      </section>
      {([ ["Category breakdown", result.category_breakdown], ["Status breakdown", result.status_breakdown] ] as const).map(([heading, breakdown]) => (
        <section className="panel" key={heading}>
          <h2>{heading}</h2>
          <table><thead><tr><th>{heading.split(" ")[0]}</th><th>Count</th><th>Percent of valid</th></tr></thead><tbody>
            {Object.entries(breakdown).map(([key, value]) => <tr key={key}><td>{key}</td><td>{value}</td><td>{result.valid_records === 0 ? "0.0%" : `${((value / result.valid_records) * 100).toFixed(1)}%`}</td></tr>)}
          </tbody></table>
        </section>
      ))}
      <section className="panel">
        <h2>Satisfaction index</h2>
        <p>Scored incidents: {result.scored_closed_incidents} of {result.closed_incidents}</p>
        <table><thead><tr><th>Score</th><th>Count</th></tr></thead><tbody>
          {Object.entries(result.satisfaction_breakdown).map(([key, value]) => <tr key={key}><td>{key}</td><td>{value}</td></tr>)}
        </tbody></table>
      </section>
    </>
  );
}