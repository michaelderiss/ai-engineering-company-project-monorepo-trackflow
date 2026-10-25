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
    // localStorage unavailable — ignore
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
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};

  // Copy caller-supplied headers
  if (options.headers) {
    const incoming = options.headers as Record<string, string>;
    for (const key of Object.keys(incoming)) {
      headers[key] = incoming[key];
    }
  }

  // Attach auth token
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Set Content-Type unless body is FormData (browser sets it automatically)
  if (
    !(options.body instanceof FormData) &&
    !headers["Content-Type"]
  ) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  // Handle 401 — session expired or invalid
  if (response.status === 401) {
    clearToken();
    redirectToLogin();
    throw new Error("Session expired. Redirecting to login.");
  }

  // Parse error responses
  if (!response.ok) {
    let message: string;
    try {
      const errorBody = await response.json();
      if (typeof errorBody?.detail === "string") {
        message = errorBody.detail;
      } else if (Array.isArray(errorBody?.detail)) {
        message = errorBody.detail
          .map((item: { msg?: string }) => item.msg)
          .filter(Boolean)
          .join(". ");
      } else {
        message = `Request failed with status ${response.status}`;
      }
    } catch {
      message = `Request failed with status ${response.status}`;
    }
    throw new Error(message);
  }

  // 204 No Content
  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
}