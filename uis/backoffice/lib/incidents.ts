import { API_BASE, clearToken, getToken, redirectToLogin } from "./auth";

export type Incident = {
  id: number;
  title: string;
  description: string;
  category: string;
  status: string;
  origin: string;
  branch: string;
  created_at: string;
  updated_at: string;
};

export type IncidentOptions = {
  branches: Record<string, string>;
  categories: Record<string, string>;
  statuses: Record<string, string>;
  origins: Record<string, string>;
  transitions: Record<string, string[]>;
};

export type IncidentSummary = {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_origin: Record<string, number>;
  by_branch: Record<string, number>;
};

export class IncidentApiError extends Error {
  constructor(message: string, public fields: Record<string, string> = {}) {
    super(message);
  }
}

export async function incidentRequest<T>(path = "", options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/incidents${path}`, {
      ...options,
      signal: options.signal ?? AbortSignal.timeout(15000),
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken() ?? ""}` },
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new IncidentApiError("Could not reach TrackFlow. Please try again.");
  }
  if (response.status === 401) {
    clearToken();
    redirectToLogin();
    throw new IncidentApiError("Your session has expired. Please sign in again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const fields = body?.errors && typeof body.errors === "object" ? body.errors : {};
    throw new IncidentApiError(
      response.status >= 500 ? "TrackFlow could not complete the request. Please try again." : body?.message ?? "Could not complete the request. Please try again.",
      fields,
    );
  }
  return response.json() as Promise<T>;
}