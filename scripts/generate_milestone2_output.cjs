const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const {
  buildMilestone2Output,
  formatMilestone2DummyOrderText,
} = require("../src/milestone2-output.js");

const repoRoot = path.join(__dirname, "..");
const testingInterfacePath = path.join(repoRoot, "src", "testing-interface.js");
const txtPath = path.join(repoRoot, ".trackflow-dummy-order.txt");
const jsonPath = path.join(repoRoot, ".trackflow-milestone2-output.json");

function extractLiteralFromFile(source, name, opener, closer) {
  const regex = new RegExp(`const\\s+${name}\\s*=\\s*(${opener}[\\s\\S]*?${closer});`);
  const match = source.match(regex);

  if (!match) {
    throw new Error(`Could not find ${name} in src/testing-interface.js`);
  }

  return vm.runInNewContext(`(${match[1]})`, { Date });
}

function loadTestingInterfaceDataset() {
  const source = fs.readFileSync(testingInterfacePath, "utf8");
  const products = extractLiteralFromFile(source, "products", "\\[", "\\]");
  const carriers = extractLiteralFromFile(source, "carriers", "\\[", "\\]");
  const shipments = extractLiteralFromFile(source, "shipments", "\\[", "\\]");

  let orderContext = { orderId: "TF-ORDER-001", client: "Northstar Outfitters" };

  if (/const\s+milestone2OrderContext\s*=/.test(source)) {
    orderContext = extractLiteralFromFile(source, "milestone2OrderContext", "\\{", "\\}");
  }

  return {
    products,
    carriers,
    shipments,
    orderId: orderContext.orderId,
    client: orderContext.client,
    selectedShipmentId: orderContext.selectedShipmentId,
  };
}

function parseShipmentArg() {
  const argument = process.argv.find((item) => item.startsWith("--shipment="));
  if (!argument) {
    const envShipment = process.env.TRACKFLOW_SHIPMENT_ID;
    return envShipment && envShipment.trim().length > 0 ? envShipment.trim() : undefined;
  }

  const value = argument.split("=")[1];
  return value && value.trim().length > 0 ? value.trim() : undefined;
}

function main() {
  let dataset;
  try {
    dataset = loadTestingInterfaceDataset();
  } catch {
    console.error("Could not load the milestone dataset. Check source access and data format, then try again.");
    return 1;
  }
  const selectedShipmentId = parseShipmentArg() ?? dataset.selectedShipmentId;
  let output;
  let txt;
  try {
    output = buildMilestone2Output({ ...dataset, selectedShipmentId });
    txt = formatMilestone2DummyOrderText(output);
  } catch {
    console.error("Could not generate milestone output. Check shipment, product, and carrier data, then try again.");
    return 1;
  }
  try {
    fs.writeFileSync(txtPath, `${txt}\n`, "utf8");
    fs.writeFileSync(jsonPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  } catch {
    console.error("Could not save milestone output. Check directory permissions and retry generation.");
    return 1;
  }
  console.log("Milestone 2 output synced.");
  return 0;
}

process.exitCode = main();
