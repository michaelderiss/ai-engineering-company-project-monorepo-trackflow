import { RequestError, requestJson, requestResponse } from "../../../packages/shared/http";
export { RequestError, isObject } from "../../../packages/shared/http";

const AUTH_TOKEN_KEY = "trackflow_access_token";

export const API_BASE =
  process.env.NEXT_PUBLIC_INCIDENTS_API_BASE_URL ?? "http://localhost:8000";

export function getToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    throw new Error("Your browser could not save the session. Allow site storage and try signing in again.");
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // localStorage unavailable — ignore
  }
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

export function redirectToLogin(): void {
  window.location.href = "/login";
}

export function redirectToHome(): void {
  window.location.href = "/";
}

/**
 * Perform a fetch against the TrackFlow API, automatically attaching the
 * stored Bearer token and handling 401 responses.
 */
function authenticatedOptions(options: RequestInit): RequestInit {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...options, headers };
}

function handleAuthError(error: unknown): never {
  if (error instanceof RequestError && error.status === 401) {
    clearToken();
    redirectToLogin();
  }
  throw error;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}, validate?: (value: unknown) => boolean): Promise<T> {
  try { return await requestJson<T>(`${API_BASE}${path}`, authenticatedOptions(options), validate); }
  catch (error) { return handleAuthError(error); }
}

export async function apiResponse(path: string, options: RequestInit = {}): Promise<Response> {
  try { return await requestResponse(`${API_BASE}${path}`, authenticatedOptions(options)); }
  catch (error) { return handleAuthError(error); }
}

export function publicApiFetch<T>(path: string, options: RequestInit = {}, validate?: (value: unknown) => boolean): Promise<T> {
  return requestJson<T>(`${API_BASE}${path}`, options, validate);
}