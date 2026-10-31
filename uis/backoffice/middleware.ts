import { NextRequest, NextResponse } from "next/server";

// Backend upstream, resolved over the Docker network by service name.
// Inside Docker compose this is http://api:8000 (set in .env/compose).
// The localhost default is only for running the app natively on the host.
const UPSTREAM = process.env.BACKEND_UPSTREAM ?? "http://localhost:8000";

/**
 * Reverse proxy for the TrackFlow API paths whose URL space overlaps with
 * frontend page routes: `/inventory/*` and `/suppliers/*` are BOTH
 * Next.js pages AND TrackFlow API endpoints.
 *
 * How we tell them apart:
 *   - Page navigation is a plain GET with no `Authorization` header.
 *   - API calls are either authenticated (GET / inventory, suppliers with
 *     a Bearer token) or mutating (POST / PATCH / DELETE).
 *
 * API-shaped requests are proxied to the backend by Docker service name
 * (`api`), never `localhost`. Everything else is rendered normally.
 */
export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  const isApiOverlap =
    pathname === "/inventory" ||
    pathname.startsWith("/inventory/") ||
    pathname === "/suppliers" ||
    pathname.startsWith("/suppliers/");

  if (!isApiOverlap) return NextResponse.next();

  const hasAuth = request.headers.get("authorization") !== null;
  const isMutating = request.method !== "GET";

  if (!hasAuth && !isMutating) return NextResponse.next();

  const target = new URL(pathname + search, UPSTREAM);
  return NextResponse.rewrite(target);
}

export const config = {
  matcher: ["/inventory", "/inventory/:path*", "/suppliers", "/suppliers/:path*"],
};