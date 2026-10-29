/**
 * FE-019 — Jest tests for packages/shared/http.ts (RequestError, requestResponse,
 * requestJson).
 *
 * Happy paths: successful fetch returns the response; valid JSON parses.
 * Failure modes: network error → safe connection-focused RequestError; 401/5xx →
 * friendly message; unreadable JSON → RequestError; validation failure → RequestError.
 */

import {
  RequestError,
  requestJson,
  requestResponse,
} from "../../../packages/shared/http";

/** Create a minimal Response-like object. */
function jsonResponse(status: number, body: unknown, ok?: boolean): Response {
  const payload = JSON.stringify(body);
  const isOk = ok ?? (status >= 200 && status < 300);
  return {
    ok: isOk,
    status,
    json: () => Promise.resolve(JSON.parse(payload)),
  } as unknown as Response;
}

/** Replace global fetch; returns the stub so tests can inspect calls. */
function stubFetch(impl: (url: string, init: RequestInit) => Promise<unknown>) {
  const stub = jest.fn(impl);
  (globalThis as Record<string, unknown>).fetch = stub;
  return stub;
}

afterEach(() => {
  delete (globalThis as Record<string, unknown>).fetch;
  jest.restoreAllMocks();
});

describe("requestResponse", () => {
  it("returns the response for a successful fetch (happy path)", async () => {
    const fetchStub = stubFetch(() => Promise.resolve(jsonResponse(200, {})));
    const response = await requestResponse("https://api.example/incidents");
    expect(response.ok).toBe(true);
    expect(fetchStub).toHaveBeenCalledWith(
      expect.stringContaining("https://api.example/incidents"),
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("throws a safe connection message on network error (failure mode)", async () => {
    stubFetch(() => Promise.reject(new TypeError("fetch failed")));
    await expect(requestResponse("https://api.example/incidents")).rejects.toThrow(
      "Could not reach the service"
    );
    // The internal error detail must never leak to the user.
    await expect(requestResponse("https://api.example/incidents")).rejects.not.toThrow(
      /fetch failed/
    );
  });

  it("maps 401 to a sign-in message (failure mode)", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(401, {})));
    await expect(requestResponse("https://api.example/me")).rejects.toMatchObject({
      status: 401,
      message: "Please sign in again to continue.",
    });
  });

  it("maps 5xx to an unavailable-service message (failure mode)", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(503, {})));
    await expect(requestResponse("https://api.example/incidents")).rejects.toMatchObject({
      status: 503,
    });
    await expect(requestResponse("https://api.example/incidents")).rejects.toThrow(
      "The service is temporarily unavailable"
    );
  });

  it("surfaces the validated inventory oversell message", async () => {
    const detail = "Insufficient stock for SKU 'TEC-EAR-001'. Available: 1, requested: 2.";
    stubFetch(() => Promise.resolve(jsonResponse(400, { detail })));

    await expect(requestResponse("https://api.example/inventory/orders/outbound"))
      .rejects.toMatchObject({ status: 400, message: detail });
  });

  it("keeps malformed inventory details generic", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(400, {
      detail: "Insufficient stock for SKU 'secret\ninternal detail'. Available: 1, requested: 2.",
    })));

    await expect(requestResponse("https://api.example/inventory/orders/outbound"))
      .rejects.toMatchObject({
        status: 400,
        message: "Could not complete the request. Please try again.",
      });
  });

  it("maps 422 without a safe detail to a generic validation message (failure mode)", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(422, { detail: "server internals" })));
    await expect(requestResponse("https://api.example/incidents")).rejects.toMatchObject({
      status: 422,
      message: "Please check the entered values and try again.",
    });
  });
});

describe("requestJson", () => {
  it("parses a valid JSON body (happy path)", async () => {
    stubFetch(() =>
      Promise.resolve(jsonResponse(200, { id: 1, title: "Incident A" }))
    );
    const data = await requestJson<{ id: number; title: string }>(
      "https://api.example/incidents/1"
    );
    expect(data).toEqual({ id: 1, title: "Incident A" });
  });

  it("returns null for a 204 response (edge case)", async () => {
    const noContent = {
      ok: true,
      status: 204,
      json: () => Promise.reject(new Error("no body")),
    } as unknown as Response;
    stubFetch(() => Promise.resolve(noContent));
    expect(await requestJson("https://api.example/incidents/1")).toBeNull();
  });

  it("throws on unreadable (non-JSON) body (failure mode)", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.reject(new SyntaxError("Unexpected token <")),
      } as unknown as Response)
    );
    await expect(requestJson("https://api.example/incidents")).rejects.toThrow(
      "unreadable response"
    );
  });

  it("throws when the payload fails the validator (failure mode)", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(200, "not-an-object")));
    await expect(
      requestJson("https://api.example/incidents", {}, () => false)
    ).rejects.toThrow("incomplete data");
  });

  it("exposes status and message via RequestError (failure mode)", async () => {
    stubFetch(() => Promise.resolve(jsonResponse(404, { detail: "nope" })));
    try {
      await requestJson("https://api.example/incidents/999");
      throw new Error("should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(RequestError);
      expect((error as RequestError).status).toBe(404);
      expect((error as RequestError).message).toContain("not found");
    }
  });
});