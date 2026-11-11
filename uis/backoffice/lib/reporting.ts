import { apiFetch } from "./auth";

export type Warehouse = "los_angeles" | "zaragoza";

export type WeeklyWarehouseClientPerformanceEntry = {
  warehouse: Warehouse;
  client_id: string;
  inbound_units_count: number;
  outbound_orders_count: number;
  stockout_events_count: number;
  discrepancy_events_count: number;
  discrepancy_rate: number;
};

export type WeeklyWarehouseClientPerformance = {
  week_start: string;
  entries: WeeklyWarehouseClientPerformanceEntry[];
};

export type PipelineRun = {
  run_id: string;
  week_start: string | null;
  queued_at: string | null;
  start_time: string | null;
  end_time: string | null;
  records_processed: number;
  rows_written: number;
  status: string;
  errors: string[];
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isEntry(value: unknown): value is WeeklyWarehouseClientPerformanceEntry {
  return isObject(value)
    && (value.warehouse === "los_angeles" || value.warehouse === "zaragoza")
    && typeof value.client_id === "string"
    && Number.isInteger(value.inbound_units_count)
    && Number.isInteger(value.outbound_orders_count)
    && Number.isInteger(value.stockout_events_count)
    && Number.isInteger(value.discrepancy_events_count)
    && typeof value.discrepancy_rate === "number"
    && Number.isFinite(value.discrepancy_rate);
}

function isWeeklyReport(value: unknown): value is WeeklyWarehouseClientPerformance {
  return isObject(value)
    && typeof value.week_start === "string"
    && Array.isArray(value.entries)
    && value.entries.every(isEntry);
}

function isPipelineRun(value: unknown): value is PipelineRun {
  return isObject(value)
    && typeof value.run_id === "string"
    && typeof value.status === "string"
    && Array.isArray(value.errors)
    && value.errors.every((error) => typeof error === "string")
    && Number.isInteger(value.records_processed)
    && Number.isInteger(value.rows_written);
}

export function getWeeklyWarehouseClientPerformance(weekStart?: string): Promise<WeeklyWarehouseClientPerformance> {
  const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
  return apiFetch(`/reporting/weekly-warehouse-client-performance${query}`, {}, isWeeklyReport);
}

export function getLatestPipelineRun(): Promise<PipelineRun> {
  return apiFetch("/reporting/pipeline-runs/latest", {}, isPipelineRun);
}

export function triggerPipelineRun(weekStart?: string): Promise<{ run_id: string; status: string }> {
  const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
  return apiFetch(`/reporting/pipeline-runs${query}`, { method: "POST" }, (value) =>
    isObject(value) && typeof value.run_id === "string" && value.status === "QUEUED",
  );
}
