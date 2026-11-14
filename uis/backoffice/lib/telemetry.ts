"use client";

export const TELEMETRY_SESSION_KEY = "trackflow_telemetry_session";
export const TELEMETRY_USER_KEY = "trackflow_telemetry_user";
export const TELEMETRY_ENDPOINT = "/api/telemetry/events";
const SCHEMA_VERSION = "1.0.0";
const MAX_EVENTS = 20;
const FLUSH_INTERVAL_MS = 10_000;
const MAX_ATTEMPTS = 3;

export const TELEMETRY_EVENT_TYPES = [
  "inbound_order_created", "outbound_order_created", "stock_threshold_triggered",
  "direct_stock_edit_rejected", "inventory_discrepancy_detected", "inventory_validation_failed",
  "inventory_products_viewed", "login_succeeded", "login_failed", "session_expired",
  "navigation_page_viewed", "flow_abandoned", "api_latency_recorded",
  "frontend_error_captured", "web_vital_recorded", "supplier_action_completed",
  "incident_action_completed",
] as const;
export type TelemetryEventType = (typeof TELEMETRY_EVENT_TYPES)[number];
export type TelemetryEvent = {
  eventId: string;
  timestamp: string;
  sessionId: string | null;
  userId: string | null;
  event_type: TelemetryEventType;
  schemaVersion: string;
  requestId: string;
  properties: Record<string, string | number | null>;
};

type PropertyRule = { required: string[]; allowed: string[] };
const rules: Record<TelemetryEventType, PropertyRule> = {
  inbound_order_created: { required: ["warehouse", "client_id", "product_id", "product_category", "quantity"], allowed: ["warehouse", "client_id", "product_id", "product_category", "quantity"] },
  outbound_order_created: { required: ["warehouse", "client_id", "product_id", "product_category", "quantity"], allowed: ["warehouse", "client_id", "product_id", "product_category", "quantity"] },
  stock_threshold_triggered: { required: ["warehouse", "client_id", "product_id", "product_category", "quantity", "minimum_stock"], allowed: ["warehouse", "client_id", "product_id", "product_category", "quantity", "minimum_stock"] },
  direct_stock_edit_rejected: { required: ["warehouse", "client_id", "product_id", "product_category", "quantity", "rejection_code"], allowed: ["warehouse", "client_id", "product_id", "product_category", "quantity", "rejection_code"] },
  inventory_discrepancy_detected: { required: ["warehouse", "client_id", "product_id", "product_category", "quantity", "system_quantity", "physical_quantity"], allowed: ["warehouse", "client_id", "product_id", "product_category", "quantity", "system_quantity", "physical_quantity"] },
  inventory_validation_failed: { required: ["operation", "validation_code", "warehouse", "product_id"], allowed: ["operation", "validation_code", "warehouse", "product_id", "product_category"] },
  inventory_products_viewed: { required: [], allowed: ["warehouse", "product_category", "result_count"] },
  login_succeeded: { required: [], allowed: ["auth_method"] },
  login_failed: { required: ["reason"], allowed: ["reason"] },
  session_expired: { required: ["reason"], allowed: ["reason"] },
  navigation_page_viewed: { required: ["route"], allowed: ["route"] },
  flow_abandoned: { required: ["flow", "last_step"], allowed: ["flow", "last_step"] },
  api_latency_recorded: { required: ["route", "method", "status_code", "duration_ms"], allowed: ["route", "method", "status_code", "duration_ms"] },
  frontend_error_captured: { required: ["error_kind", "error_code", "route"], allowed: ["error_kind", "error_code", "route"] },
  web_vital_recorded: { required: ["metric_name", "value", "route"], allowed: ["metric_name", "value", "route"] },
  supplier_action_completed: { required: ["action", "result"], allowed: ["action", "result"] },
  incident_action_completed: { required: ["action", "result"], allowed: ["action", "result"] },
};
const routes = ["/", "/inventory/products", "/inventory/orders", "/inventory/orders/inbound", "/inventory/orders/outbound", "/suppliers", "/incidents", "/incident-file-analyzer", "/account/profile"];
const apiRoutes = ["/auth/login", "/auth/me", "/users", "/profiles/me", "/inventory/products", "/inventory/orders", "/suppliers", "/api/incidents"];
let queue: TelemetryEvent[] = [];
let timer: number | undefined;

function uuid(): string | null {
  try { return globalThis.crypto.randomUUID(); } catch { return null; }
}
function enabled(): boolean {
  const value = process.env.NEXT_PUBLIC_TELEMETRY_ENABLED?.trim().toLowerCase();
  return !["0", "false", "no", "off"].includes(value ?? "") && typeof window !== "undefined";
}
function safeRoute(api = false): string | null {
  const route = window.location.pathname;
  return (api ? apiRoutes : routes).includes(route) ? route : null;
}
function ensureSession(): { sessionId: string; userId: string } | null {
  try {
    if (!localStorage.getItem("trackflow_access_token")) return null;
    let sessionId = sessionStorage.getItem(TELEMETRY_SESSION_KEY);
    let userId = sessionStorage.getItem(TELEMETRY_USER_KEY);
    if (!sessionId || !userId) {
      sessionId = uuid(); userId = uuid();
      if (!sessionId || !userId) return null;
      sessionStorage.setItem(TELEMETRY_SESSION_KEY, sessionId);
      sessionStorage.setItem(TELEMETRY_USER_KEY, userId);
    }
    return { sessionId, userId };
  } catch { return null; }
}
function validProperties(type: TelemetryEventType, properties: Record<string, unknown>): boolean {
  const rule = rules[type];
  return Object.keys(properties).every((key) => rule.allowed.includes(key)) && rule.required.every((key) => key in properties);
}
function makeEvent(type: TelemetryEventType, properties: Record<string, unknown>): TelemetryEvent | null {
  if (!validProperties(type, properties)) return null;
  const identity = ensureSession();
  const cleanProperties: Record<string, string | number | null> = {};
  for (const [key, value] of Object.entries(properties)) {
    if (value === null || typeof value === "string" || (typeof value === "number" && Number.isFinite(value))) cleanProperties[key] = value as string | number | null;
    else return null;
  }
  const eventId = uuid(); const requestId = uuid();
  if (!eventId || !requestId) return null;
  return { eventId, timestamp: new Date().toISOString(), sessionId: identity?.sessionId ?? null, userId: identity?.userId ?? null, event_type: type, schemaVersion: SCHEMA_VERSION, requestId, properties: cleanProperties };
}

async function deliver(events: TelemetryEvent[], attempt = 0): Promise<void> {
  try {
    const response = await fetch(TELEMETRY_ENDPOINT, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ events }), keepalive: true, credentials: "same-origin" });
    if (!response.ok) throw new Error("delivery failed");
  } catch {
    if (attempt + 1 < MAX_ATTEMPTS) {
      window.setTimeout(() => { void deliver(events, attempt + 1); }, [1000, 2000, 4000][attempt]);
    }
  }
}
function flush(): void {
  if (!queue.length || !enabled()) return;
  const batch = queue.splice(0, MAX_EVENTS);
  void deliver(batch);
}
export function startTelemetry(): void {
  if (!enabled() || timer) return;
  timer = window.setInterval(flush, FLUSH_INTERVAL_MS);
  document.addEventListener("visibilitychange", onVisibilityChange);
}
function onVisibilityChange(): void {
  if (document.visibilityState !== "hidden" || !queue.length || !enabled()) return;
  const batch = queue.splice(0, MAX_EVENTS);
  try {
    const blob = new Blob([JSON.stringify({ events: batch })], { type: "application/json" });
    if (!navigator.sendBeacon(TELEMETRY_ENDPOINT, blob)) void deliver(batch);
  } catch { void deliver(batch); }
}
export function trackTelemetry(type: TelemetryEventType, properties: Record<string, unknown> = {}): void {
  if (!enabled() || !TELEMETRY_EVENT_TYPES.includes(type)) return;
  const event = makeEvent(type, properties);
  if (!event) return;
  queue.push(event);
  if (queue.length >= MAX_EVENTS) flush();
}
export function trackLoginFailure(reason: "invalid_credentials" | "network_error" | "rate_limited"): void {
  if (!enabled()) return;
  const eventId = uuid(); const requestId = uuid();
  if (!eventId || !requestId) return;
  queue.push({ eventId, timestamp: new Date().toISOString(), sessionId: null, userId: null, event_type: "login_failed", schemaVersion: SCHEMA_VERSION, requestId, properties: { reason } });
  if (queue.length >= MAX_EVENTS) flush();
}
export function beginTelemetrySession(): void {
  try {
    if (!localStorage.getItem("trackflow_access_token")) return;
    const sessionId = uuid(); const userId = uuid();
    if (sessionId && userId) {
      sessionStorage.setItem(TELEMETRY_SESSION_KEY, sessionId);
      sessionStorage.setItem(TELEMETRY_USER_KEY, userId);
    }
  } catch { /* best effort only */ }
}
export function resetTelemetrySession(): void {
  beginTelemetrySession();
}
export function clearTelemetrySession(): void {
  try { sessionStorage.removeItem(TELEMETRY_SESSION_KEY); sessionStorage.removeItem(TELEMETRY_USER_KEY); } catch { /* best effort only */ }
}
export function trackSafePageView(): void {
  const route = safeRoute();
  if (route) trackTelemetry("navigation_page_viewed", { route });
}
