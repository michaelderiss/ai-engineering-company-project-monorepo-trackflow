"use client";

import { FormEvent, useEffect, useState } from "react";
import { Incident, IncidentApiError, IncidentOptions, IncidentSummary, incidentRequest } from "../../lib/incidents";

const EMPTY_FORM = { title: "", description: "", category: "", status: "open", origin: "", branch: "central" };
const EMPTY_FILTERS = { status: "", origin: "", branch: "", category: "" };
type FormFields = typeof EMPTY_FORM;

export default function IncidentsPage() {
  const [options, setOptions] = useState<IncidentOptions | null>(null);
  const [optionsError, setOptionsError] = useState("");
  const [optionsRevision, setOptionsRevision] = useState(0);
  const [form, setForm] = useState<FormFields>({ ...EMPTY_FORM });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS });
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [updateError, setUpdateError] = useState("");
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [listRevision, setListRevision] = useState(0);
  const [summary, setSummary] = useState<IncidentSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState("");
  const [summaryRevision, setSummaryRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setOptionsError("");
    incidentRequest<IncidentOptions>("/options").then((data) => {
      if (active) setOptions(data);
    }).catch(() => {
      if (active) setOptionsError("Could not load incident options. Please retry.");
    });
    return () => { active = false; };
  }, [optionsRevision]);

  useEffect(() => {
    let active = true;
    setListLoading(true);
    setListError("");
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== ""));
    incidentRequest<Incident[]>(`?${query}`).then((data) => {
      if (active) setIncidents(data);
    }).catch(() => {
      if (active) setListError("Could not load incidents. Please retry.");
    }).finally(() => { if (active) setListLoading(false); });
    return () => { active = false; };
  }, [filters, listRevision]);

  useEffect(() => {
    let active = true;
    setSummaryLoading(true);
    setSummaryError("");
    incidentRequest<IncidentSummary>("/summary").then((data) => {
      if (active) setSummary(data);
    }).catch(() => {
      if (active) setSummaryError("Could not load the summary. Please retry.");
    }).finally(() => { if (active) setSummaryLoading(false); });
    return () => { active = false; };
  }, [summaryRevision]);

  function refresh() {
    setListRevision((value) => value + 1);
    setSummaryRevision((value) => value + 1);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSuccess("");
    setFormError("");
    const errors: Record<string, string> = {};
    for (const [field, value] of Object.entries(form)) {
      if (!value.trim()) errors[field] = "This field is required.";
    }
    if (form.title.trim().length > 120) errors.title = "Please use 120 characters or fewer.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      setFormError("Please check the highlighted fields.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await incidentRequest<Incident>("", { method: "POST", body: JSON.stringify(form) });
      setForm({ ...EMPTY_FORM });
      setSuccess(`Incident #${created.id} registered successfully.`);
      refresh();
    } catch (error) {
      if (error instanceof IncidentApiError) {
        setFieldErrors(error.fields);
        setFormError(error.message);
      } else setFormError("Could not register the incident. Please try again.");
    } finally { setSubmitting(false); }
  }

  async function changeStatus(record: Incident, status: string) {
    if (updatingId !== null) return;
    setUpdateError("");
    setUpdatingId(record.id);
    setIncidents((rows) => rows.map((row) => row.id === record.id ? { ...row, status } : row));
    try {
      await incidentRequest<Incident>(`/${record.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      refresh();
    } catch {
      setIncidents((rows) => rows.map((row) => row.id === record.id ? record : row));
      setUpdateError(`Could not update incident #${record.id}. Its previous status has been restored.`);
    } finally { setUpdatingId(null); }
  }

  function updateField(field: keyof FormFields, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: "" }));
  }

  function selectField(field: keyof Pick<FormFields, "category" | "status" | "origin" | "branch">, label: string, choices: Record<string, string>) {
    return (
      <label className={field === "branch" && form.origin === "branch" ? "incident-branch-highlight" : ""}>
        {label} <span className="required">*</span>
        <select className="selector" value={form[field]} onChange={(event) => updateField(field, event.target.value)} required aria-invalid={!!fieldErrors[field]} aria-describedby={fieldErrors[field] ? `error-${field}` : undefined}>
          <option value="">Select {label.toLowerCase()}</option>
          {Object.entries(choices).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select>
        {fieldErrors[field] && <span id={`error-${field}`} className="error field-error">{fieldErrors[field]}</span>}
      </label>
    );
  }

  return (
    <main className="incident-manager">
      <header className="panel-header">
        <h1>Incident Manager</h1>
        <a className="text-link" href="/">Operations Home</a>
      </header>
      <nav className="incident-nav" aria-label="Incident sections">
        <a href="#register">Register incident</a>
        <a href="#incident-list">Incident list</a>
        <a href="#incident-summary">Summary</a>
      </nav>

      <section id="register" className="incident-section" aria-labelledby="register-heading">
        <h2 id="register-heading">Register Incident</h2>
        {optionsError && <p role="alert" className="error">{optionsError} <button type="button" onClick={() => setOptionsRevision((value) => value + 1)}>Retry options</button></p>}
        {!options && !optionsError && <p role="status">Loading incident options...</p>}
        <form className="stack" onSubmit={submit} noValidate aria-busy={submitting}>
          <fieldset className="incident-fields" disabled={submitting || !options}>
            <label>
              Title <span className="required">*</span>
              <input className="text-input" value={form.title} onChange={(event) => updateField("title", event.target.value)} maxLength={120} required aria-invalid={!!fieldErrors.title} aria-describedby={fieldErrors.title ? "error-title" : undefined} />
              {fieldErrors.title && <span id="error-title" className="error field-error">{fieldErrors.title}</span>}
            </label>
            <label>
              Description <span className="required">*</span>
              <textarea className="text-input" rows={4} value={form.description} onChange={(event) => updateField("description", event.target.value)} required aria-invalid={!!fieldErrors.description} aria-describedby={fieldErrors.description ? "error-description" : undefined} />
              {fieldErrors.description && <span id="error-description" className="error field-error">{fieldErrors.description}</span>}
            </label>
            {options && <div className="form-grid">
              {selectField("category", "Category", options.categories)}
              {selectField("status", "Status", options.statuses)}
              {selectField("origin", "Origin", options.origins)}
              {selectField("branch", "Branch", options.branches)}
            </div>}
            <div className="actions"><button type="submit" disabled={submitting || !options}>{submitting ? "Registering..." : "Register incident"}</button></div>
          </fieldset>
          {formError && <p role="alert" className="error">{formError}</p>}
          {success && <p role="status" className="success">{success}</p>}
        </form>
      </section>

      <section id="incident-list" className="incident-section" aria-labelledby="list-heading" aria-busy={listLoading}>
        <div className="panel-header"><h2 id="list-heading">Incidents</h2><button type="button" disabled={listLoading || updatingId !== null} onClick={() => setListRevision((value) => value + 1)}>Refresh list</button></div>
        <fieldset className="incident-fields filter-grid" disabled={updatingId !== null || !options}>
          {options && ([ ["status", options.statuses], ["origin", options.origins], ["branch", options.branches], ["category", options.categories] ] as const).map(([field, choices]) => (
            <label key={field}>{field.charAt(0).toUpperCase() + field.slice(1)} filter
              <select className="selector" value={filters[field]} onChange={(event) => setFilters((current) => ({ ...current, [field]: event.target.value }))}>
                <option value="">All {field === "category" ? "categories" : field === "status" ? "statuses" : `${field}s`}</option>
                {Object.entries(choices).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          ))}
        </fieldset>
        {updateError && <p role="alert" className="error">{updateError}</p>}
        {listLoading ? <p role="status">Loading incidents...</p> : listError ? (
          <div role="alert"><p className="error">{listError}</p><button type="button" onClick={() => setListRevision((value) => value + 1)}>Retry incidents</button></div>
        ) : incidents.length === 0 ? <p role="status">No incidents match the current filters.</p> : (
          <>
            <p>{incidents.length} incident{incidents.length === 1 ? "" : "s"}</p>
            <div className="incident-table-scroll">
              <table className="incident-table">
                <caption className="sr-only">Registered TrackFlow incidents</caption>
                <thead><tr><th scope="col">Incident</th><th scope="col">Category</th><th scope="col">Origin / Branch</th><th scope="col">Status</th><th scope="col">Created / Updated</th></tr></thead>
                <tbody>{incidents.map((record) => (
                  <tr key={record.id}>
                    <td><strong>#{record.id} {record.title}</strong><details><summary>Description</summary><p>{record.description}</p></details></td>
                    <td>{options?.categories[record.category] ?? record.category}</td>
                    <td>{options?.origins[record.origin] ?? record.origin}<br />{options?.branches[record.branch] ?? record.branch}</td>
                    <td>
                      {(options?.transitions[record.status]?.length ?? 0) > 0 ? (
                        <select className="selector" aria-label={`Status for incident ${record.id}`} value={record.status} disabled={updatingId !== null || listLoading} onChange={(event) => changeStatus(record, event.target.value)}>
                          <option value={record.status}>{options?.statuses[record.status]}</option>
                          {options?.transitions[record.status].map((next) => <option key={next} value={next}>{options.statuses[next]}</option>)}
                        </select>
                      ) : <span>{options?.statuses[record.status] ?? record.status}</span>}
                      {updatingId === record.id && <span role="status">Saving...</span>}
                    </td>
                    <td><time dateTime={record.created_at}>{new Date(record.created_at).toLocaleString()}</time><br /><time dateTime={record.updated_at}>{new Date(record.updated_at).toLocaleString()}</time></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section id="incident-summary" className="incident-section" aria-labelledby="summary-heading" aria-busy={summaryLoading}>
        <h2 id="summary-heading">Summary</h2>
        {summaryLoading ? <p role="status">Loading summary...</p> : summaryError ? (
          <div role="alert"><p className="error">{summaryError}</p><button type="button" onClick={() => setSummaryRevision((value) => value + 1)}>Retry summary</button></div>
        ) : summary && (
          <>
            <p className="incident-total">Total incidents: <strong>{summary.total}</strong></p>
            <div className="incident-summary-grid">
              {([
                ["Status", summary.by_status, options?.statuses], ["Category", summary.by_category, options?.categories],
                ["Origin", summary.by_origin, options?.origins], ["Branch", summary.by_branch, options?.branches],
              ] as const).map(([name, counts, labels]) => (
                <section key={name}><h3>By {name.toLowerCase()}</h3><dl>{Object.entries(counts).map(([key, count]) => <div key={key}><dt>{labels?.[key] ?? key}</dt><dd>{count}</dd></div>)}</dl></section>
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}