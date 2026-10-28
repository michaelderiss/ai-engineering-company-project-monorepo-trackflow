import { apiFetch, isObject, RequestError } from "./auth";

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

export { RequestError as IncidentApiError };

export async function incidentRequest<T>(path = "", options: RequestInit = {}): Promise<T> {
  return apiFetch<T>(`/api/incidents${path}`, options, (value) => {
    if (path === "/options") return isObject(value) && ["branches", "categories", "statuses", "origins"].every((key) => isObject(value[key]) && Object.values(value[key]).every((label) => typeof label === "string")) && isObject(value.transitions) && Object.values(value.transitions).every((next) => Array.isArray(next) && next.every((status) => typeof status === "string"));
    if (path === "/summary") return isObject(value) && typeof value.total === "number" && ["by_status", "by_category", "by_origin", "by_branch"].every((key) => isObject(value[key]) && Object.values(value[key]).every((count) => typeof count === "number"));
    const validIncident = (item: unknown) => isObject(item) && typeof item.id === "number" && ["title", "description", "status", "origin", "branch", "category", "created_at", "updated_at"].every((key) => typeof item[key] === "string");
    return Array.isArray(value) ? value.every(validIncident) : validIncident(value);
  });
}