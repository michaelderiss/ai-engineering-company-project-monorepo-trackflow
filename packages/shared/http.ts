export class RequestError extends Error {
  constructor(message: string, public status = 0, public fields: Record<string, string> = {}) {
    super(message);
    this.name = "RequestError";
  }
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

const SAFE_MESSAGES = new Set([
  "Incorrect email or password", "The current password is incorrect.",
  "A user with this email already exists.", "This user already has a profile.",
  "This password reset link is invalid, expired, or has already been used.",
  "This field is required.", "Please choose an available option.", "Please enter a value.",
  "Please use 120 characters or fewer.", "Please enter a valid value.",
]);

function isSafeMessage(value: unknown): value is string {
  return typeof value === "string" && (
    SAFE_MESSAGES.has(value) ||
    /^Insufficient stock for SKU '[A-Za-z0-9._-]{1,80}'\. Available: \d+, requested: \d+\.$/.test(value)
  );
}

export async function requestResponse(url: string, options: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    const headers = new Headers(options.headers);
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    response = await fetch(url, { ...options, headers, signal: options.signal ?? AbortSignal.timeout(15000), cache: "no-store" });
  } catch {
    throw new RequestError("Could not reach the service. Check your connection and try again.");
  }
  if (response.ok) return response;
  let body: unknown;
  try { body = await response.json(); } catch { body = null; }
  const fields: Record<string, string> = {};
  if (isObject(body) && isObject(body.errors)) {
    for (const [field, value] of Object.entries(body.errors)) {
      if (field !== "__proto__" && field !== "constructor") {
        fields[field] = isSafeMessage(value) ? value : "Please check this field.";
      }
    }
  }
  const detail = isObject(body) ? body.message ?? body.detail : null;
  let message = "Could not complete the request. Please try again.";
  if (response.status >= 500) message = "The service is temporarily unavailable. Please try again shortly.";
  else if (response.status === 401) message = "Please sign in again to continue.";
  else if (response.status === 403) message = "You do not have permission to do this. Return home or contact support.";
  else if (response.status === 404) message = "The requested item was not found. Return home or try again.";
  else if (Object.keys(fields).length) message = "Please check the highlighted fields and try again.";
  else if (isSafeMessage(detail)) message = detail;
  else if (response.status === 422) message = "Please check the entered values and try again.";
  throw new RequestError(message, response.status, fields);
}

export async function requestJson<T>(url: string, options: RequestInit = {}, validate: (value: unknown) => boolean = (value) => isObject(value) || Array.isArray(value)): Promise<T> {
  const response = await requestResponse(url, options);
  if (response.status === 204) return null as T;
  let data: unknown;
  try { data = await response.json(); } catch {
    throw new RequestError("The service returned an unreadable response. Please try again.");
  }
  if (!validate(data)) throw new RequestError("The service returned incomplete data. Please try again.");
  return data as T;
}