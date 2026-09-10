function roundTo2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function calculatePriorityMultiplier(priority) {
  if (priority === "Express") {
    return 1.3;
  }

  if (priority === "Same-day") {
    return 1.6;
  }

  return 1;
}

function calculateShippingCost(shipment, product, carrier) {
  const baseRate = carrier.baseRateUSD;
  const weightCost = product.weightKg * carrier.ratePerKgUSD * shipment.quantity;
  const distanceCost = shipment.destination.distanceKm * carrier.ratePerKmUSD;
  const subtotal = baseRate + weightCost + distanceCost;

  return roundTo2(subtotal * calculatePriorityMultiplier(shipment.priority));
}

function scoreCarrierForShipment(carrier, shipment, product) {
  let score = 0;

  if (carrier.operatesIn.includes(shipment.destination.country)) {
    score += 20;
  }

  if (product.weightKg * shipment.quantity <= carrier.maxWeightKg) {
    score += 20;
  }

  if (carrier.acceptsPriority.includes(shipment.priority)) {
    score += 15;
  }

  if (!product.isFragile || carrier.handlesFragile) {
    score += 15;
  }

  score += carrier.onTimeRate * 0.3;

  return roundTo2(score);
}

function selectBestCarrier(carriers, shipment, product) {
  let best = null;

  for (const carrier of carriers) {
    const score = scoreCarrierForShipment(carrier, shipment, product);

    if (score < 50) {
      continue;
    }

    const cost = calculateShippingCost(shipment, product, carrier);

    if (best === null || cost < best.cost) {
      best = { carrier, score, cost };
    }
  }

  return best;
}

function findProductBySKU(products, sku) {
  const normalized = sku.trim().toLowerCase();
  return products.find((product) => product.sku.toLowerCase() === normalized) ?? null;
}

function estimateDeliveryWindow(priority, avgDeliveryDays) {
  if (priority === "Same-day") {
    return "same day";
  }

  if (priority === "Express") {
    return "1 to 2 business days";
  }

  return avgDeliveryDays <= 2 ? "2 to 3 business days" : "2 to 4 business days";
}

function buildMilestone2Output({ products, carriers, shipments, orderId, client }) {
  const shipment = shipments[0];
  const product = shipment ? findProductBySKU(products, shipment.sku) : null;

  if (!shipment || !product) {
    return {
      orderId: orderId ?? "Unavailable",
      client: client ?? "Unavailable",
      destination: "Unavailable",
      urgency: "Unavailable",
      totalWeight: "Unavailable",
      selectedCarrier: "Unavailable",
      carrierReason: "Shipment or product data is missing.",
      assignedWarehouse: "Unavailable",
      warehouseReason: "Shipment or product data is missing.",
      trackingId: "Unavailable",
      expectedDeliveryWindow: "Unavailable",
      cxNote: "Milestone 2 output could not be generated due to missing shipment data.",
      selectedCarrierCostUSD: 0,
      selectedCarrierScore: 0,
    };
  }

  const best = selectBestCarrier(carriers, shipment, product);
  const carrierName = best?.carrier.name ?? "DHL Express";
  const deliveryWindow = best
    ? estimateDeliveryWindow(shipment.priority, best.carrier.avgDeliveryDays)
    : "2 to 4 business days";
  const assignedWarehouse = shipment.origin;

  return {
    orderId: orderId ?? shipment.id,
    client: client ?? "TrackFlow Demo Client",
    destination: `${shipment.destination.city}, ${shipment.destination.country}`,
    urgency: shipment.priority,
    totalWeight: `${roundTo2(product.weightKg * shipment.quantity)} kg`,
    selectedCarrier: carrierName,
    carrierReason: best
      ? `Selected via Milestone 2 scoring (score ${best.score}) and cost optimization (USD ${best.cost}).`
      : "No carrier met the score threshold, so fallback carrier was used.",
    assignedWarehouse,
    warehouseReason: `Shipment origin ${shipment.origin} is used for this milestone planning scenario.`,
    trackingId: `TF-${carrierName.replace(/\s+/g, "-").toUpperCase()}-${shipment.id}`,
    expectedDeliveryWindow: deliveryWindow,
    cxNote: `Parcel planned from ${shipment.origin} with ${carrierName}. Share ${deliveryWindow} expectation with customer support.`,
    selectedCarrierCostUSD: best?.cost ?? 0,
    selectedCarrierScore: best?.score ?? 0,
  };
}

function formatMilestone2DummyOrderText(output) {
  return [
    "TRACKFLOW DUMMY ORDER",
    "",
    "Input Summary",
    `- Order ID: ${output.orderId}`,
    `- Client: ${output.client}`,
    `- Destination: ${output.destination}`,
    `- Urgency: ${output.urgency}`,
    `- Total Weight: ${output.totalWeight}`,
    "",
    "Warehouse Assignment",
    `- Assigned warehouse: ${output.assignedWarehouse}`,
    `- Reason: ${output.warehouseReason}`,
    "",
    "Carrier Decision",
    `- Selected carrier: ${output.selectedCarrier}`,
    `- Reason: ${output.carrierReason}`,
    "",
    "Tracking and Delivery",
    `- Dummy tracking ID: ${output.trackingId}`,
    `- Expected delivery window: ${output.expectedDeliveryWindow}`,
    `- CX note: ${output.cxNote}`,
    "",
    "Computed Metrics",
    `- Selected carrier score: ${output.selectedCarrierScore}`,
    `- Selected carrier cost (USD): ${output.selectedCarrierCostUSD}`,
  ].join("\n");
}

const defaultMilestone2Dataset = {
  products: [
    {
      sku: "SHOE-BLK-42",
      name: "Black Running Shoes - Size 42",
      category: "Fashion",
      weightKg: 0.8,
      dimensions: { lengthCm: 35, widthCm: 22, heightCm: 12 },
      warehouse: "Los Angeles",
      stockQuantity: 45,
      minStockThreshold: 20,
      unitCostUSD: 35.0,
      isFragile: false,
      status: "Active",
    },
    {
      sku: "LAPTOP-DELL-15",
      name: "Dell Laptop 15 inch",
      category: "Electronics",
      weightKg: 2.3,
      dimensions: { lengthCm: 40, widthCm: 28, heightCm: 3 },
      warehouse: "Zaragoza",
      stockQuantity: 8,
      minStockThreshold: 10,
      unitCostUSD: 650.0,
      isFragile: true,
      status: "Low stock",
    },
    {
      sku: "PERFUME-COCO-50",
      name: "Coco Perfume 50ml",
      category: "Cosmetics",
      weightKg: 0.3,
      dimensions: { lengthCm: 12, widthCm: 8, heightCm: 15 },
      warehouse: "Los Angeles",
      stockQuantity: 120,
      minStockThreshold: 30,
      unitCostUSD: 85.0,
      isFragile: true,
      status: "Active",
    },
  ],
  carriers: [
    {
      id: "CAR-UPS",
      name: "UPS",
      operatesIn: ["United States"],
      baseRateUSD: 5.0,
      ratePerKgUSD: 1.2,
      ratePerKmUSD: 0.05,
      avgDeliveryDays: 3,
      onTimeRate: 88,
      maxWeightKg: 30,
      handlesFragile: true,
      acceptsPriority: ["Standard", "Express"],
    },
    {
      id: "CAR-SEUR",
      name: "SEUR",
      operatesIn: ["Spain"],
      baseRateUSD: 6.5,
      ratePerKgUSD: 1.5,
      ratePerKmUSD: 0.08,
      avgDeliveryDays: 2,
      onTimeRate: 92,
      maxWeightKg: 25,
      handlesFragile: true,
      acceptsPriority: ["Standard", "Express", "Same-day"],
    },
    {
      id: "CAR-DHL",
      name: "DHL Express",
      operatesIn: ["United States", "Spain"],
      baseRateUSD: 12.0,
      ratePerKgUSD: 2.0,
      ratePerKmUSD: 0.1,
      avgDeliveryDays: 1,
      onTimeRate: 95,
      maxWeightKg: 50,
      handlesFragile: true,
      acceptsPriority: ["Express", "Same-day"],
    },
  ],
  shipments: [
    {
      id: "SH-2024-8821",
      sku: "LAPTOP-DELL-15",
      quantity: 1,
      origin: "Zaragoza",
      destination: {
        city: "Madrid",
        country: "Spain",
        postalCode: "28001",
        distanceKm: 320,
      },
      priority: "Express",
      declaredValueUSD: 650.0,
      carrier: null,
      status: "Pending",
      createdAt: "2024-03-15T00:00:00.000Z",
    },
  ],
  orderId: "TF-ORDER-001",
  client: "Northstar Outfitters",
};

const api = {
  calculateShippingCost,
  scoreCarrierForShipment,
  selectBestCarrier,
  buildMilestone2Output,
  formatMilestone2DummyOrderText,
  defaultMilestone2Dataset,
};

if (typeof window !== "undefined") {
  window.TrackFlowMilestone2Output = api;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = api;
}
