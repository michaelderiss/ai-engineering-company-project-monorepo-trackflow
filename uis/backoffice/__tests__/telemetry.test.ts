import {
  beginTelemetrySession,
  canonicalApiRoute,
  clearTelemetrySession,
  getTelemetryEndpoint,
  startTelemetry,
  stopTelemetry,
  TELEMETRY_SESSION_KEY,
  TELEMETRY_USER_KEY,
  trackApiLatency,
  trackFrontendError,
  trackInventoryOrderCreated,
  trackTelemetry,
  trackWebVital,
} from "../lib/telemetry";

class MemoryStorage {
  private values = new Map<string, string>();
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, String(value)); }
  removeItem(key: string) { this.values.delete(key); }
}

describe("telemetry capture service", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: new MemoryStorage() });
    Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: new MemoryStorage() });
    Object.defineProperty(globalThis, "window", { configurable: true, value: { setInterval, clearInterval, setTimeout, location: { pathname: "/" } } });
    Object.defineProperty(globalThis, "document", { configurable: true, value: { addEventListener: jest.fn(), removeEventListener: jest.fn(), visibilityState: "visible" } });
    global.fetch = jest.fn().mockResolvedValue({ ok: true }) as jest.Mock;
    Object.defineProperty(globalThis, "crypto", { configurable: true, value: { randomUUID: jest.fn().mockReturnValue("00000000-0000-4000-8000-000000000001") } });
    process.env.NEXT_PUBLIC_TELEMETRY_ENABLED = "true";
  });

  afterEach(() => {
    stopTelemetry();
    jest.useRealTimers();
    delete process.env.NEXT_PUBLIC_TELEMETRY_ENABLED;
    delete process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT;
  });

  it("creates two opaque session IDs only when an auth token exists", () => {
    beginTelemetrySession();
    expect(sessionStorage.getItem(TELEMETRY_SESSION_KEY)).toBeNull();
    localStorage.setItem("trackflow_access_token", "never-send-this");
    beginTelemetrySession();
    expect(sessionStorage.getItem(TELEMETRY_SESSION_KEY)).toMatch(/^[0-9a-f-]{36}$/);
    expect(sessionStorage.getItem(TELEMETRY_USER_KEY)).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("drops properties outside the strict event allowlist", () => {
    localStorage.setItem("trackflow_access_token", "test");
    trackTelemetry("navigation_page_viewed", { route: "/", email: "private@example.test" });
    jest.advanceTimersByTime(10_000);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("queues valid events and posts only the allowlisted envelope", async () => {
    localStorage.setItem("trackflow_access_token", "test");
    startTelemetry();
    trackTelemetry("navigation_page_viewed", { route: "/" });
    jest.advanceTimersByTime(10_000);
    await Promise.resolve();
    jest.clearAllTimers();
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledWith("/api/telemetry/events", expect.objectContaining({ method: "POST" }));
    const [, init] = (fetch as jest.Mock).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.events).toHaveLength(1);
    expect(body.events[0]).toMatchObject({ event_type: "navigation_page_viewed", properties: { route: "/" } });
    expect(JSON.stringify(body)).not.toContain("test");
  });

  it("uses the environment-configured endpoint when present", () => {
    process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT = "https://telemetry.example.test/events";
    expect(getTelemetryEndpoint()).toBe("https://telemetry.example.test/events");
  });

  it("captures API timing, safe errors, and Web Vitals with canonical routes", async () => {
    startTelemetry();
    expect(canonicalApiRoute("/inventory/products/7")).toBe("/inventory/products");
    trackApiLatency("/inventory/products/7", "GET", 200, 12.5);
    trackFrontendError("window_error");
    trackWebVital("LCP", 1200);
    jest.advanceTimersByTime(10_000);
    await Promise.resolve();

    const [, init] = (fetch as jest.Mock).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.events.map((event: { event_type: string }) => event.event_type)).toEqual([
      "api_latency_recorded",
      "frontend_error_captured",
      "web_vital_recorded",
    ]);
    expect(JSON.stringify(body)).not.toContain("message");
  });

  it("uses only the explicitly approved client ID mapping for inventory events", async () => {
    startTelemetry();
    trackInventoryOrderCreated("inbound_order_created", {
      client_name: "PureStep Footwear",
      sku: "CLT-SNK-W-42",
      category: "fashion",
      warehouse: "LA",
    }, 3);
    trackInventoryOrderCreated("inbound_order_created", {
      client_name: "Unmapped Brand",
      sku: "UNKNOWN-1",
      category: "fashion",
      warehouse: "LA",
    }, 1);
    jest.advanceTimersByTime(10_000);
    await Promise.resolve();

    const [, init] = (fetch as jest.Mock).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.events).toHaveLength(1);
    expect(body.events[0]).toMatchObject({
      event_type: "inbound_order_created",
      properties: {
        client_id: "purestep_footwear",
        product_id: "CLT-SNK-W-42",
        warehouse: "los_angeles",
        quantity: 3,
      },
    });
  });

  it("clears session identity on logout", () => {
    sessionStorage.setItem(TELEMETRY_SESSION_KEY, "session");
    sessionStorage.setItem(TELEMETRY_USER_KEY, "user");
    clearTelemetrySession();
    expect(sessionStorage.getItem(TELEMETRY_SESSION_KEY)).toBeNull();
    expect(sessionStorage.getItem(TELEMETRY_USER_KEY)).toBeNull();
  });
});
