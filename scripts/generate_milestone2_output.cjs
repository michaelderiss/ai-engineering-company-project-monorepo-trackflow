const fs = require("node:fs");
const path = require("node:path");

const {
  buildMilestone2Output,
  formatMilestone2DummyOrderText,
  defaultMilestone2Dataset,
} = require("../src/milestone2-output.js");

const repoRoot = path.join(__dirname, "..");
const txtPath = path.join(repoRoot, ".trackflow-dummy-order.txt");
const jsonPath = path.join(repoRoot, ".trackflow-milestone2-output.json");

const output = buildMilestone2Output(defaultMilestone2Dataset);
const txt = formatMilestone2DummyOrderText(output);

fs.writeFileSync(txtPath, `${txt}\n`, "utf8");
fs.writeFileSync(jsonPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");

console.log(`Milestone 2 output synced:`);
console.log(`- ${path.relative(repoRoot, txtPath)}`);
console.log(`- ${path.relative(repoRoot, jsonPath)}`);
