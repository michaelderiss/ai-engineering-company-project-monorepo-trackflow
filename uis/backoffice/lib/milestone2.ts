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
  warehouseReason: "Milestone 2 output file was not found.",
  selectedCarrier: "Unavailable",
  carrierReason: "Milestone 2 output file was not found.",
  trackingId: "Unavailable",
  expectedDeliveryWindow: "Unavailable",
  cxNote: "Run the dummy-order simulation to regenerate .trackflow-dummy-order.txt.",
};

function extractLineValue(text: string, label: string): string {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = text.match(new RegExp(`- ${escaped}:\\s*(.+)`, "i"));
  return match?.[1]?.trim() ?? "Unavailable";
}

function extractWarehouseSection(text: string): { assignedWarehouse: string; warehouseReason: string } {
  const match = text.match(
    /Warehouse Assignment[\s\S]*?- Assigned warehouse:\s*(.+)\r?\n- Reason:\s*(.+)/i,
  );

  return {
    assignedWarehouse: match?.[1]?.trim() ?? "Unavailable",
    warehouseReason: match?.[2]?.trim() ?? "Unavailable",
  };
}

function extractCarrierSection(text: string): { selectedCarrier: string; carrierReason: string } {
  const match = text.match(
    /Carrier Decision[\s\S]*?- Selected carrier:\s*(.+)\r?\n- Reason:\s*(.+)/i,
  );

  return {
    selectedCarrier: match?.[1]?.trim() ?? "Unavailable",
    carrierReason: match?.[2]?.trim() ?? "Unavailable",
  };
}

export function readMilestone2Order(): Milestone2Order {
  try {
    const jsonPath = join(process.cwd(), "..", "..", ".trackflow-milestone2-output.json");
    const jsonPayload = JSON.parse(readFileSync(jsonPath, "utf8")) as Milestone2Order;

    return jsonPayload;
  } catch {
    // Fall back to text parsing when JSON artifact does not exist yet.
  }

  try {
    const filePath = join(process.cwd(), "..", "..", ".trackflow-dummy-order.txt");
    const output = readFileSync(filePath, "utf8");

    const warehouse = extractWarehouseSection(output);
    const carrier = extractCarrierSection(output);

    return {
      orderId: extractLineValue(output, "Order ID"),
      client: extractLineValue(output, "Client"),
      destination: extractLineValue(output, "Destination"),
      urgency: extractLineValue(output, "Urgency"),
      totalWeight: extractLineValue(output, "Total Weight"),
      assignedWarehouse: warehouse.assignedWarehouse,
      warehouseReason: warehouse.warehouseReason,
      selectedCarrier: carrier.selectedCarrier,
      carrierReason: carrier.carrierReason,
      trackingId: extractLineValue(output, "Dummy tracking ID"),
      expectedDeliveryWindow: extractLineValue(output, "Expected delivery window"),
      cxNote: extractLineValue(output, "CX note"),
    };
  } catch {
    return FALLBACK_ORDER;
  }
}
