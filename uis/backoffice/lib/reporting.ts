import { isObject } from "../../../packages/shared/http";
import { API_BASE, clearToken, getToken, redirectToLogin } from "./auth";

export type ReportingEntry = {
  warehouse: string;
  client_id: string;
  inbound_units_count: number;
  outbound_orders_count: number;
  stockout_events_count: number;
  discrepancy_events_count: number;
  discrepancy_rate: number;
};

export type WeeklyPerformance = {
  week_start: string | null;
  entries: ReportingEntry[];
};

export type PipelineRun = {
  run_id: number;
  week_start: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  records_extracted: number | null;
  records_loaded: number | null;
  triggered_by: string;
};

function getApiBase(): string {
  return (process.env.NEXT_PUBLIC_INCIDENTS_API_BASE_URL ?? API_BASE).replace(/\/+$/, "");
}

function isReportingEntry(value: unknown): value is ReportingEntry {
  return (
    isObject(value) &&
    typeof value.warehouse === "string" &&
    typeof value.client_id === "string" &&
    typeof value.inbound_units_count === "number" &&
    typeof value.outbound_orders_count === "number" &&
    typeof value.stockout_events_count === "number" &&
    typeof value.discrepancy_events_count === "number" &&
    typeof value.discrepancy_rate === "number"
  );
}

function isWeeklyPerformance(value: unknown): value is WeeklyPerformance {
  return (
    isObject(value) &&
    (value.week_start === null || typeof value.week_start === "string") &&
    Array.isArray(value.entries) &&
    value.entries.every(isReportingEntry)
  );
}

function isPipelineRun(value: unknown): value is PipelineRun {
  return (
    isObject(value) &&
    typeof value.run_id === "number" &&
    typeof value.week_start === "string" &&
    typeof value.started_at === "string" &&
    (value.completed_at === null || typeof value.completed_at === "string") &&
    typeof value.status === "string" &&
    typeof value.triggered_by === "string"
  );
}

async function reportingRequest<T>(
  path: string,
  options: RequestInit = {},
  validate?: (value: unknown) => boolean,
): Promise<T> {
  const token = getToken();
  if (!token) {
    redirectToLogin();
    throw new Error("Please sign in again to continue.");
  }

  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);

  try {
    const { requestJson } = await import("../../../packages/shared/http");
    return await requestJson<T>(`${getApiBase()}/reporting${path}`, {
      ...options,
      headers,
    }, validate);
  } catch (error) {
    const { RequestError } = await import("../../../packages/shared/http");
    if (error instanceof RequestError && error.status === 401) {
      clearToken();
      redirectToLogin();
    }
    throw error;
  }
}

export function getWeeklyPerformance(weekStart?: string): Promise<WeeklyPerformance> {
  const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
  return reportingRequest<WeeklyPerformance>(
    `/weekly-warehouse-client-performance${query}`,
    {},
    isWeeklyPerformance,
  );
}

export function getLatestPipelineRun(): Promise<PipelineRun | null> {
  return reportingRequest<PipelineRun | null>(
    "/pipeline-runs/latest",
    {},
    (value) => value === null || isPipelineRun(value),
  );
}

export function triggerPipelineRun(weekStart?: string): Promise<PipelineRun> {
  const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
  return reportingRequest<PipelineRun>(
    "/pipeline-runs",
    { method: "POST" },
    isPipelineRun,
  );
}