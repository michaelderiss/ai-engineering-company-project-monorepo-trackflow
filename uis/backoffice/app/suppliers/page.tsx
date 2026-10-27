"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { apiFetch, isObject } from "../../lib/auth";

const CATEGORY_OPTIONS = [
  "carrier_last_mile",
  "carrier_international",
  "warehouse_supplies",
  "packaging_materials",
  "reverse_logistics",
  "fleet_maintenance",
  "it_and_wms_software",
  "cleaning_and_facilities",
] as const;

const COUNTRY_OPTIONS = ["USA", "Spain"] as const;
const STATUS_OPTIONS = ["active", "suspended"] as const;
const CURRENCY_BY_COUNTRY = {
  USA: "USD",
  Spain: "EUR",
} as const;

type Supplier = {
  id: number;
  name: string;
  country: "USA" | "Spain";
  categories: string[];
  rate_per_shipment: number;
  currency: "USD" | "EUR";
  updated_at: string;
  status: "active" | "suspended";
  service_zone?: string | null;
  contact_email?: string | null;
  notes?: string | null;
};

type SupplierFormState = {
  name: string;
  country: "USA" | "Spain";
  categories: string[];
  rate_per_shipment: string;
  currency: "USD" | "EUR";
  status: "active" | "suspended";
  service_zone: string;
  contact_email: string;
  notes: string;
};

const EMPTY_FORM: SupplierFormState = {
  name: "",
  country: "USA",
  categories: ["carrier_last_mile"],
  rate_per_shipment: "",
  currency: "USD",
  status: "active",
  service_zone: "",
  contact_email: "",
  notes: "",
};

function normalizeOptional(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

function validSupplier(value: unknown): boolean {
  return isObject(value) && typeof value.id === "number" && typeof value.name === "string" && typeof value.rate_per_shipment === "number" && ["country", "currency", "status", "updated_at"].every((field) => typeof value[field] === "string") && Array.isArray(value.categories) && value.categories.every((item) => typeof item === "string") && ["service_zone", "notes", "contact_email"].every((field) => value[field] == null || typeof value[field] === "string");
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [countryFilter, setCountryFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [form, setForm] = useState<SupplierFormState>(EMPTY_FORM);
  const [rateDrafts, setRateDrafts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("");
  const loadVersion = useRef(0);

  useEffect(() => {
    void loadSuppliers();
  }, [countryFilter, categoryFilter]);

  async function loadSuppliers(): Promise<void> {
    const version = ++loadVersion.current;
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (countryFilter) {
        params.set("country", countryFilter);
      }
      if (categoryFilter) {
        params.set("category", categoryFilter);
      }

      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await apiFetch<Supplier[]>(`/suppliers${suffix}`, {}, (value) => Array.isArray(value) && value.every(validSupplier));
      if (version !== loadVersion.current) return;
      setSuppliers(data);
      setRateDrafts(
        Object.fromEntries(data.map((supplier) => [supplier.id, supplier.rate_per_shipment.toString()])),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unexpected error.";
      if (version === loadVersion.current) setError(message);
    } finally {
      if (version === loadVersion.current) setLoading(false);
    }
  }

  function toggleCategory(category: string): void {
    setForm((current) => {
      const exists = current.categories.includes(category);
      const nextCategories = exists
        ? current.categories.filter((item) => item !== category)
        : [...current.categories, category];

      return {
        ...current,
        categories: nextCategories,
      };
    });
  }

  function validateForm(): string | null {
    if (!form.name.trim()) {
      return "Supplier name is required.";
    }
    if (form.categories.length === 0) {
      return "Select at least one category.";
    }
    const rate = Number(form.rate_per_shipment);
    if (!Number.isFinite(rate) || rate <= 0) {
      return "Rate per shipment must be greater than zero.";
    }
    const expectedCurrency = CURRENCY_BY_COUNTRY[form.country];
    if (form.currency !== expectedCurrency) {
      return `Suppliers from ${form.country} must use ${expectedCurrency}.`;
    }
    return null;
  }

  async function onCreateSupplier(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setSubmitting(true);
    setFormError(null);
    setFeedback("");

    try {
      const payload = {
        name: form.name.trim(),
        country: form.country,
        categories: form.categories,
        rate_per_shipment: Number(form.rate_per_shipment),
        currency: form.currency,
        status: form.status,
        service_zone: normalizeOptional(form.service_zone),
        contact_email: normalizeOptional(form.contact_email),
        notes: normalizeOptional(form.notes),
      };

      await apiFetch<Supplier>("/suppliers", {
        method: "POST",
        body: JSON.stringify(payload),
      }, validSupplier);

      setForm(EMPTY_FORM);
      setFeedback("Supplier registered successfully.");
      await loadSuppliers();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unexpected error.";
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  }

  async function updateRate(supplierId: number): Promise<void> {
    if (savingId !== null) return;
    const draft = rateDrafts[supplierId] ?? "";
    const rate = Number(draft);
    if (!Number.isFinite(rate) || rate <= 0) {
      setError("Updated rate must be greater than zero.");
      return;
    }

    setError(null);
    setFeedback("");
    setSavingId(supplierId);
    try {
      await apiFetch(`/suppliers/${supplierId}/rate`, { method: "PATCH", body: JSON.stringify({ rate_per_shipment: rate }) }, validSupplier);
      setFeedback("Supplier rate updated.");
      await loadSuppliers();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not save the rate. Please try again.");
    } finally {
      setSavingId(null);
    }
  }

  async function toggleStatus(supplier: Supplier): Promise<void> {
    if (savingId !== null) return;
    setError(null);
    setFeedback("");
    const nextStatus = supplier.status === "active" ? "suspended" : "active";
    setSavingId(supplier.id);
    try {
      await apiFetch(`/suppliers/${supplier.id}/status`, { method: "PATCH", body: JSON.stringify({ status: nextStatus }) }, validSupplier);
      setFeedback("Supplier status updated.");
      await loadSuppliers();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not update the status. Please try again.");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <main>
      <h1>Supplier Directory</h1>
      <p>
        Centralized supplier registry for TrackFlow operations across USA and Spain.
      </p>

      <section className="panel">
        <div className="panel-header">
          <h2>Filters</h2>
          <a href="/" className="launcher-link">
            Back to launcher
          </a>
        </div>
        <div className="filter-grid">
          <label>
            Country
            <select
              className="selector"
              value={countryFilter}
              onChange={(event) => setCountryFilter(event.target.value)}
            >
              <option value="">All countries</option>
              {COUNTRY_OPTIONS.map((country) => (
                <option key={country} value={country}>
                  {country}
                </option>
              ))}
            </select>
          </label>
          <label>
            Category
            <select
              className="selector"
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value)}
            >
              <option value="">All categories</option>
              {CATEGORY_OPTIONS.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error && <div role="alert"><p className="error">{error}</p><button type="button" disabled={loading} onClick={() => void loadSuppliers()}>Retry loading suppliers</button></div>}
        {feedback && <p role="status" className="success">{feedback}</p>}
      </section>

      <section className="panel">
        <h2>Register supplier</h2>
        <form className="stack" onSubmit={onCreateSupplier}>
          <div className="form-grid">
            <label>
              Name
              <input
                className="text-input"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
              />
            </label>
            <label>
              Country
              <select
                className="selector"
                value={form.country}
                onChange={(event) => {
                  const country = event.target.value as SupplierFormState["country"];
                  setForm({
                    ...form,
                    country,
                    currency: CURRENCY_BY_COUNTRY[country],
                  });
                }}
              >
                {COUNTRY_OPTIONS.map((country) => (
                  <option key={country} value={country}>
                    {country}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Rate per shipment
              <input
                className="text-input"
                type="number"
                min="0.01"
                step="0.01"
                value={form.rate_per_shipment}
                onChange={(event) =>
                  setForm({ ...form, rate_per_shipment: event.target.value })
                }
                required
              />
            </label>
            <label>
              Currency
              <select
                className="selector"
                value={form.currency}
                onChange={(event) =>
                  setForm({
                    ...form,
                    currency: event.target.value as SupplierFormState["currency"],
                  })
                }
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </label>
            <label>
              Status
              <select
                className="selector"
                value={form.status}
                onChange={(event) =>
                  setForm({
                    ...form,
                    status: event.target.value as SupplierFormState["status"],
                  })
                }
              >
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Service zone
              <input
                className="text-input"
                value={form.service_zone}
                onChange={(event) => setForm({ ...form, service_zone: event.target.value })}
              />
            </label>
            <label>
              Contact email
              <input
                className="text-input"
                type="email"
                value={form.contact_email}
                onChange={(event) =>
                  setForm({ ...form, contact_email: event.target.value })
                }
              />
            </label>
            <label>
              Notes
              <input
                className="text-input"
                value={form.notes}
                onChange={(event) => setForm({ ...form, notes: event.target.value })}
              />
            </label>
          </div>

          <fieldset className="category-fieldset">
            <legend>Categories</legend>
            <div className="category-grid">
              {CATEGORY_OPTIONS.map((category) => (
                <label key={category} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.categories.includes(category)}
                    onChange={() => toggleCategory(category)}
                  />
                  <span>{category}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {formError && <p className="error">{formError}</p>}

          <div className="actions">
            <button type="submit" disabled={submitting}>
              {submitting ? "Saving..." : "Register supplier"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Supplier list</h2>
          <p className="launcher-note">
            {loading ? "Loading suppliers..." : `${suppliers.length} supplier records`}
          </p>
        </div>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Country</th>
              <th>Categories</th>
              <th>Rate</th>
              <th>Status</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {!loading && !error && suppliers.length === 0 && <tr><td colSpan={7}>No suppliers match the current filters.</td></tr>}
            {suppliers.map((supplier) => (
              <tr key={supplier.id}>
                <td>
                  <strong>{supplier.name}</strong>
                  {supplier.service_zone ? <div>{supplier.service_zone}</div> : null}
                </td>
                <td>{supplier.country}</td>
                <td>{supplier.categories.join(", ")}</td>
                <td>
                  <div className="rate-editor">
                    <input
                      className="text-input small-input"
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={rateDrafts[supplier.id] ?? supplier.rate_per_shipment.toString()}
                      onChange={(event) =>
                        setRateDrafts({
                          ...rateDrafts,
                          [supplier.id]: event.target.value,
                        })
                      }
                    />
                    <span>{supplier.currency}</span>
                  </div>
                </td>
                <td>
                  <span
                    className={supplier.status === "active" ? "status-badge active" : "status-badge suspended"}
                  >
                    {supplier.status}
                  </span>
                </td>
                <td>{new Date(supplier.updated_at).toLocaleString()}</td>
                <td>
                  <div className="table-actions">
                    <button type="button" disabled={savingId !== null || loading} onClick={() => void updateRate(supplier.id)}>
                      {savingId === supplier.id ? "Saving..." : "Update rate"}
                    </button>
                    <button type="button" disabled={savingId !== null || loading} onClick={() => void toggleStatus(supplier)}>
                      {supplier.status === "active" ? "Suspend" : "Reactivate"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
