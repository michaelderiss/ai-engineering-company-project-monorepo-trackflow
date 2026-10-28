import { readFileSync } from "node:fs";
import { join } from "node:path";

export type Milestone2Order = {
  orderId: string;
  client: string;
  destination: string;
  urgency: string;
  totalWeight: string;
  assignedWarehouse: string;
  warehouseReason: string;
  selectedCarrier: string;
  carrierReason: string;
  trackingId: string;
  expectedDeliveryWindow: string;
  cxNote: string;
};

const FALLBACK_ORDER: Milestone2Order = {
  orderId: "Unavailable",
  client: "Unavailable",
  destination: "Unavailable",
  urgency: "Unavailable",
  totalWeight: "Unavailable",
  assignedWarehouse: "Unavailable",
  warehouseReason: "Generated Milestone 2 output was not found.",
  selectedCarrier: "Unavailable",
  carrierReason: "Generated Milestone 2 output was not found.",
  trackingId: "Unavailable",
  expectedDeliveryWindow: "Unavailable",
  cxNote: "Dispatch information is unavailable. Reload this page or contact operations support.",
};

export function readMilestone2Order(): Milestone2Order {
  const jsonPath = join(process.cwd(), "..", "..", ".trackflow-milestone2-output.json");
  let text: string;
  try {
    text = readFileSync(jsonPath, "utf8");
  } catch {
    console.warn("Dispatch output could not be loaded; showing the unavailable state.");
    return FALLBACK_ORDER;
  }
  let jsonPayload: unknown;
  try { jsonPayload = JSON.parse(text); } catch {
    console.warn("Dispatch output could not be parsed; showing the unavailable state.");
    return FALLBACK_ORDER;
  }
  if (!jsonPayload || typeof jsonPayload !== "object" || !Object.keys(FALLBACK_ORDER).every((key) => typeof (jsonPayload as Record<string, unknown>)[key] === "string")) {
    console.warn("Dispatch output is incomplete; showing the unavailable state.");
    return FALLBACK_ORDER;
  }
  return jsonPayload as Milestone2Order;
}
