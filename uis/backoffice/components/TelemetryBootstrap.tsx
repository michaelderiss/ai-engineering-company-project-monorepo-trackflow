"use client";

import { useEffect } from "react";
import { startTelemetry, trackSafePageView } from "../lib/telemetry";

export function TelemetryBootstrap() {
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_TELEMETRY_ENABLED === "false") return;
    startTelemetry();
    trackSafePageView();
  }, []);
  return null;
}
