const assert = require("node:assert/strict");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const context = await browser.newContext({ viewport });
      await context.addInitScript(() => {
        localStorage.setItem("trackflow_access_token", "synthetic-browser-only");
        window.formatCalls = 0;
        const original = Date.prototype.toLocaleString;
        Date.prototype.toLocaleString = function (...args) {
          window.formatCalls += 1;
          return original.apply(this, args);
        };
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const chunks = new Map();
      const pendingChunks = [];
      page.on("response", (response) => {
        if (response.url().includes("/_next/static/") && response.url().endsWith(".js")) {
          pendingChunks.push(response.text().then((text) => chunks.set(response.url(), text)));
        }
      });
      const orders = Array.from({ length: 40007 }, (_, index) => ({
        id: index + 1, order_type: "inbound", sku_id: 1, quantity: 20 + index % 30,
        reference: `PO-${index}`, exit_type: null, tracking_number: null,
        warehouse: index % 2 ? "LA" : "ZGZ", created_at: new Date(Date.UTC(2026, 0, 1) + index * 60000).toISOString(),
        user_uuid: "1", sku: { id: 1, name: "Synthetic sneaker", sku: "LOAD-1", client_name: "Brand 1", category: "fashion", warehouse: "LA" },
      }));
      let releaseOrders;
      const ordersReady = new Promise((resolve) => { releaseOrders = resolve; });
      let historyRequests = 0;
      const corsHeaders = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };
      await page.route("**/*", async (route) => {
        const request = route.request();
        if (!["fetch", "xhr"].includes(request.resourceType())) return route.continue();
        const path = new URL(request.url()).pathname;
        if (path === "/inventory/orders") {
          historyRequests += 1;
          if (historyRequests === 1) await ordersReady;
          return route.fulfill({ headers: corsHeaders, json: orders });
        }
        if (path === "/api/incidents/analyze") {
          return route.fulfill({ headers: corsHeaders, json: {
            source_file: "synthetic.csv", total_records: 100, valid_records: 95, invalid_records: 5,
            invalid_breakdown: { invalid_country: 5 }, category_breakdown: { carrier_issue: 95 },
            status_breakdown: { open: 95 }, country_breakdown: { USA: 95 },
            satisfaction_breakdown: { "4": 10 }, satisfaction_average: 4, scored_closed_incidents: 10, closed_incidents: 10,
          } });
        }
        return route.continue();
      });
      const base = process.env.CACHING_UI_URL || "http://localhost:3101";
      await page.goto(`${base}/inventory/orders`);
      await page.getByText("Loading order history…").waitFor();
      await Promise.all(pendingChunks);
      assert(![...chunks.values()].some((text) => text.includes("Previous history page")), "History chunk loaded before data");
      releaseOrders();
      try {
        await page.getByRole("button", { name: "Next history page" }).waitFor();
      } catch (error) {
        console.error({ historyRequests, errors, url: page.url(), body: await page.locator("body").innerText() });
        throw error;
      }
      assert.equal(await page.locator("tbody tr").count(), 50);
      const initialCalls = await page.evaluate(() => window.formatCalls);
      assert.equal(initialCalls, orders.length);
      await page.getByRole("button", { name: "Next history page" }).click();
      await page.getByText("Page 2 of 801", { exact: false }).waitFor();
      assert.equal(await page.evaluate(() => window.formatCalls), initialCalls);
      await page.getByRole("button", { name: "Refresh history" }).click();
      await page.getByRole("button", { name: "Next history page" }).waitFor();
      assert.equal(await page.evaluate(() => window.formatCalls), initialCalls * 2);
      await page.screenshot({ path: `/tmp/trackflow-history-${viewport.width}.png`, fullPage: true });
      chunks.clear();
      pendingChunks.length = 0;
      await page.goto(`${base}/incident-file-analyzer`);
      await page.waitForLoadState("networkidle");
      await Promise.all(pendingChunks);
      assert(![...chunks.values()].some((text) => text.includes("Invalid country")), "Report chunk loaded before analysis");
      await page.locator('input[type="file"]').setInputFiles({ name: "synthetic.csv", mimeType: "text/csv", buffer: Buffer.from("synthetic") });
      await page.getByRole("button", { name: "Analyze incidents", exact: true }).click();
      await page.getByRole("heading", { name: "General metrics" }).waitFor();
      await page.waitForLoadState("networkidle");
      await Promise.all(pendingChunks);
      const reportChunk = [...chunks.entries()].find(([, text]) => text.includes("Invalid country"));
      assert(reportChunk, "Report did not load a separate chunk after analysis");
      assert.equal(await page.getByRole("button", { name: "Download results CSV" }).isEnabled(), true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
      await page.screenshot({ path: `/tmp/trackflow-analyzer-${viewport.width}.png`, fullPage: true });
      assert.deepEqual(errors, []);
      console.log(JSON.stringify({ viewport, historyRows: orders.length, renderedRows: 50, formattingCallsAfterPageChange: initialCalls,
        formattingCallsAfterRefresh: initialCalls * 2, lazyReportBytes: Buffer.byteLength(reportChunk[1]), errors }));
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });