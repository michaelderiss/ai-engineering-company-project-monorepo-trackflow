/**
 * FE-019 — Jest tests for uis/backoffice/lib/incidents.ts incidentRequest validator.
 *
 * incidentRequest delegates to apiFetch, which parses the body and then runs an
 * inline validator. Happy path: a well-formed incident (or list) passes. Failure
 * mode: malformed payloads (missing id, wrong field types, wrong summary shape)
 * are refused with a RequestError, so incomplete data never reaches the UI.
 */

import { IncidentApiError, incidentRequest } from "../lib/incidents";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

function stubFetch(body: unknown, status = 200) {
  const stub = jest.fn(() => Promise.resolve(jsonResponse(status, body)));
  (globalThis as Record<string, unknown>).fetch = stub;
  // incidentRequest attaches a Bearer token from localStorage via apiFetch.
  (globalThis as Record<string, unknown>).localStorage = {
    getItem: jest.fn((key: string) => (key === "trackflow_access_token" ? "tok" : null)),
  } as unknown as Storage;
  return stub;
}

const wellFormedIncident = {
  id: 7,
  title: "Late delivery",
  description: "Arrived after the SLA window",
  category: "carrier_last_mile",
  status: "open",
  origin: "api",
  branch: "LAX",
  created_at: "2026-10-27T12:00:00Z",
  updated_at: "2026-10-27T12:05:00Z",
};

afterEach(() => {
  delete (globalThis as Record<string, unknown>).fetch;
  delete (globalThis as Record<string, unknown>).localStorage;
  jest.restoreAllMocks();
});

describe("incidentRequest — single incident", () => {
  it("accepts a well-formed incident (happy path)", async () => {
    stubFetch(wellFormedIncident);
    const incident = await incidentRequest<typeof wellFormedIncident>("/7");
    expect(incident.id).toBe(7);
    expect(incident.title).toBe("Late delivery");
  });

  it("rejects an incident missing its id (failure mode)", async () => {
    stubFetch({ ...wellFormedIncident, id: undefined });
    await expect(incidentRequest("/7")).rejects.toThrow("incomplete data");
  });

  it("rejects an incident with a non-string title (failure mode)", async () => {
    stubFetch({ ...wellFormedIncident, title: 42 });
    await expect(incidentRequest("/7")).rejects.toThrow("incomplete data");
  });
});

describe("incidentRequest — incident list", () => {
  it("accepts a well-formed list (happy path)", async () => {
    stubFetch([wellFormedIncident]);
    const list = await incidentRequest<unknown[]>("/");
    expect(list).toHaveLength(1);
  });

  it("rejects a list containing a malformed entry (failure mode)", async () => {
    stubFetch([wellFormedIncident, { ...wellFormedIncident, created_at: null }]);
    await expect(incidentRequest("/")).rejects.toThrow("incomplete data");
  });
});

describe("incidentRequest — options and summary", () => {
  it("accepts a well-formed options payload (happy path)", async () => {
    const options = {
      branches: { LAX: "Los Angeles" },
      categories: { open: "Open" },
      statuses: { open: "Open" },
      origins: { api: "API" },
      transitions: { open: ["closed"] },
    };
    stubFetch(options);
    const result = await incidentRequest<unknown>("/options");
    expect(result).toEqual(options);
  });

  it("rejects options with a malformed transitions map (failure mode)", async () => {
    const options = {
      branches: {},
      categories: {},
      statuses: {},
      origins: {},
      transitions: { open: [42] },
    };
    stubFetch(options);
    await expect(incidentRequest("/options")).rejects.toThrow("incomplete data");
  });

  it("accepts a well-formed summary payload (happy path)", async () => {
    const summary = {
      total: 3,
      by_status: { open: 3 },
      by_category: { carrier_last_mile: 3 },
      by_origin: { api: 3 },
      by_branch: { LAX: 3 },
    };
    stubFetch(summary);
    const result = await incidentRequest<unknown>("/summary");
    expect(result).toEqual(summary);
  });

  it("rejects a summary whose total is not a number (failure mode)", async () => {
    const summary = {
      total: "three",
      by_status: {},
      by_category: {},
      by_origin: {},
      by_branch: {},
    };
    stubFetch(summary);
    await expect(incidentRequest("/summary")).rejects.toThrow("incomplete data");
  });
});

describe("incidentRequest — transport failures", () => {
  it("surfaces a RequestError when the service is unreachable (failure mode)", async () => {
    (globalThis as Record<string, unknown>).fetch = jest.fn(() =>
      Promise.reject(new TypeError("network down"))
    );
    await expect(incidentRequest("/")).rejects.toBeInstanceOf(IncidentApiError);
    await expect(incidentRequest("/")).rejects.toThrow("Could not reach the service");
  });
});