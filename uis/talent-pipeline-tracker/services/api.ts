import { RequestError, requestJson } from "../../../packages/shared/http";

const BASE_URL =
  process.env.NEXT_PUBLIC_TRACKER_API_BASE_URL ?? "https://playground.4geeks.com/tracker/api/v1";

export { RequestError as ApiError };

export function request<T>(path: string, options: RequestInit = {}, validate?: (value: unknown) => boolean): Promise<T> {
  return requestJson<T>(`${BASE_URL}${path}`, options, validate);
}
