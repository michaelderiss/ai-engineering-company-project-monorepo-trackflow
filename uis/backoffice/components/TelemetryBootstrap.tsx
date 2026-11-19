"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from "web-vitals";
import {
  canonicalApiRoute,
  startTelemetry,
  stopTelemetry,
  telemetryEnabled,
  trackApiLatency,
  trackFrontendError,
  trackSafePageView,
  trackWebVital,
} from "../lib/telemetry";

export function TelemetryBootstrap() {
  const pathname = usePathname();

  useEffect(() => {
    if (!telemetryEnabled()) return;
    startTelemetry();

    const originalFetch = window.fetch;
    window.fetch = async (input, init) => {
      const requestUrl = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
      let route: string | null = null;
      try {
        const url = new URL(requestUrl, window.location.href);
        const configuredApiUrls = [
          process.env.NEXT_PUBLIC_INCIDENTS_API_BASE_URL,
          process.env.NEXT_PUBLIC_INVENTORY_API_URL,
        ].filter((value): value is string => Boolean(value?.trim()));
        const allowedOrigins = new Set([window.location.origin]);
        for (const baseUrl of configuredApiUrls) {
          try { allowedOrigins.add(new URL(baseUrl).origin); } catch { /* Ignore invalid optional API URLs. */ }
        }
        if (allowedOrigins.has(url.origin)) route = canonicalApiRoute(url.pathname);
      } catch { /* Ignore non-URL fetch inputs. */ }

      const started = performance.now();
      const response = await originalFetch.call(window, input, init);
      if (route) trackApiLatency(route, method, response.status, performance.now() - started);
      return response;
    };

    const onWindowError = () => trackFrontendError("window_error");
    const onUnhandledRejection = () => trackFrontendError("unhandled_rejection");
    window.addEventListener("error", onWindowError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);

    const reportVital = (metric: Metric) => {
      if (["CLS", "FCP", "INP", "LCP", "TTFB"].includes(metric.name)) {
        trackWebVital(metric.name as "CLS" | "FCP" | "INP" | "LCP" | "TTFB", metric.value);
      }
    };
    onCLS(reportVital);
    onFCP(reportVital);
    onINP(reportVital);
    onLCP(reportVital);
    onTTFB(reportVital);

    return () => {
      window.fetch = originalFetch;
      window.removeEventListener("error", onWindowError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
      stopTelemetry();
    };
  }, []);

  useEffect(() => {
    if (telemetryEnabled() && pathname) trackSafePageView();
  }, [pathname]);

  return null;
}
