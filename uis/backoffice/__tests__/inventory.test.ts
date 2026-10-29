import {
  createInventoryProduct,
  createStockExit,
  createStockEntry,
  getInventoryProduct,
  getInventoryOrders,
  getInventoryProducts,
} from "../lib/inventory";

function installStorage(token: string): void {
  const store = new Map([["trackflow_access_token", token]]);
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
      removeItem: (key: string) => store.delete(key),
    },
  });
}

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

beforeEach(() => {
  process.env.NEXT_PUBLIC_INVENTORY_API_URL = "http://inventory.test/";
  installStorage("test-bearer-token");
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).localStorage;
  delete (globalThis as Record<string, unknown>).fetch;
  delete process.env.NEXT_PUBLIC_INVENTORY_API_URL;
  jest.restoreAllMocks();
});

describe("inventory API client", () => {
  it("loads validated products from the configured API with bearer auth", async () => {
    const product = {
      id: 1,
      name: "White Sneaker",
      sku: "CLT-SNK-W-42",
      client_name: "PureStep Footwear",
      category: "fashion",
      warehouse: "LA",
      current_stock: 25,
    };
    const fetchStub = jest.fn((_url: string, _init: RequestInit) =>
      Promise.resolve(response([product])),
    );
    (globalThis as Record<string, unknown>).fetch = fetchStub;

    await expect(getInventoryProducts()).resolves.toEqual([product]);

    expect(fetchStub).toHaveBeenCalledWith(
      "http://inventory.test/inventory/products",
      expect.objectContaining({ cache: "no-store" }),
    );
    const request = fetchStub.mock.calls[0][1] as RequestInit;
    expect(new Headers(request.headers).get("Authorization")).toBe(
      "Bearer test-bearer-token",
    );
  });

  it("posts inbound movements through the client integration layer", async () => {
    const entry = {
      id: 7,
      sku_id: 1,
      quantity: 3,
      reference: "PO-TEST-1001",
      warehouse: "LA",
      created_at: "2026-10-28T12:00:00Z",
      user_uuid: "12",
    };
    const fetchStub = jest.fn(() => Promise.resolve(response(entry, 201)));
    (globalThis as Record<string, unknown>).fetch = fetchStub;

    await expect(createStockEntry({
      sku_id: 1,
      quantity: 3,
      reference: "PO-TEST-1001",
      warehouse: "LA",
    })).resolves.toEqual(entry);

    expect(fetchStub).toHaveBeenCalledWith(
      "http://inventory.test/inventory/orders/inbound",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("creates a product and fetches its detail through the client", async () => {
    const product = {
      id: 2,
      name: "Fast Charger",
      sku: "TEC-CHG-065",
      client_name: "SoundWave Electronics",
      category: "electronics",
      warehouse: "ZGZ",
      current_stock: 0,
    };
    const fetchStub = jest.fn((_url: string, _init: RequestInit) =>
      Promise.resolve(response(product)),
    );
    fetchStub.mockResolvedValueOnce(response(product, 201));
    (globalThis as Record<string, unknown>).fetch = fetchStub;

    await expect(createInventoryProduct({
      name: product.name,
      sku: product.sku,
      client_name: product.client_name,
      category: "electronics",
      warehouse: "ZGZ",
    })).resolves.toEqual(product);
    await expect(getInventoryProduct(product.id)).resolves.toEqual(product);

    expect(fetchStub.mock.calls.map(([url]) => url)).toEqual([
      "http://inventory.test/inventory/products",
      "http://inventory.test/inventory/products/2",
    ]);
  });

  it("records outbound movements and validates history with SKU details", async () => {
    const stockExit = {
      id: 8,
      sku_id: 1,
      quantity: 1,
      exit_type: "dispatch",
      tracking_number: "TRACK-TEST-1001",
      warehouse: "LA",
      created_at: "2026-10-28T12:00:00Z",
      user_uuid: "12",
    };
    const order = {
      id: stockExit.id,
      order_type: "outbound",
      sku_id: stockExit.sku_id,
      quantity: stockExit.quantity,
      reference: null,
      exit_type: stockExit.exit_type,
      tracking_number: stockExit.tracking_number,
      warehouse: stockExit.warehouse,
      created_at: stockExit.created_at,
      user_uuid: stockExit.user_uuid,
      sku: {
        id: 1,
        name: "White Sneaker",
        sku: "CLT-SNK-W-42",
        client_name: "PureStep Footwear",
        category: "fashion",
        warehouse: "LA",
      },
    };
    const fetchStub = jest.fn((_url: string, _init: RequestInit) =>
      Promise.resolve(response(stockExit, 201)),
    );
    fetchStub
      .mockResolvedValueOnce(response(stockExit, 201))
      .mockResolvedValueOnce(response([order]));
    (globalThis as Record<string, unknown>).fetch = fetchStub;

    await expect(createStockExit({
      sku_id: 1,
      quantity: 1,
      exit_type: "dispatch",
      tracking_number: "TRACK-TEST-1001",
      warehouse: "LA",
    })).resolves.toEqual(stockExit);
    await expect(getInventoryOrders()).resolves.toEqual([order]);

    expect(fetchStub.mock.calls.map(([url]) => url)).toEqual([
      "http://inventory.test/inventory/orders/outbound",
      "http://inventory.test/inventory/orders",
    ]);
  });

  it("rejects malformed product payloads", async () => {
    (globalThis as Record<string, unknown>).fetch = jest.fn(() =>
      Promise.resolve(response([{ id: 1, sku: "missing-required-fields" }])),
    );

    await expect(getInventoryProducts()).rejects.toThrow("incomplete data");
  });
});