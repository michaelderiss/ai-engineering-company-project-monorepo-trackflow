import { isObject, RequestError } from "../../../packages/shared/http";
import {
  API_BASE,
  clearToken,
  getToken,
  redirectToLogin,
} from "./auth";

export type Warehouse = "LA" | "ZGZ";
export type InventoryCategory = "fashion" | "electronics" | "cosmetics";
export type ExitType = "dispatch" | "loss";

export type InventoryProduct = {
  id: number;
  name: string;
  sku: string;
  client_name: string;
  category: InventoryCategory;
  warehouse: Warehouse;
  current_stock: number;
};

export type StockEntry = {
  id: number;
  sku_id: number;
  quantity: number;
  reference: string;
  warehouse: Warehouse;
  created_at: string;
  user_uuid: string;
};

export type StockExit = {
  id: number;
  sku_id: number;
  quantity: number;
  exit_type: ExitType;
  tracking_number: string | null;
  warehouse: Warehouse;
  created_at: string;
  user_uuid: string;
};

export type InventoryOrder = {
  id: number;
  order_type: "inbound" | "outbound";
  sku_id: number;
  quantity: number;
  reference: string | null;
  exit_type: ExitType | null;
  tracking_number: string | null;
  warehouse: Warehouse;
  created_at: string;
  user_uuid: string;
  sku: Omit<InventoryProduct, "current_stock">;
};

export type CreateProduct = Omit<InventoryProduct, "id" | "current_stock">;
export type CreateStockEntry = Omit<StockEntry, "id" | "created_at" | "user_uuid">;
export type CreateStockExit = Omit<StockExit, "id" | "created_at" | "user_uuid">;

function getApiBase(): string {
  return (
    process.env.NEXT_PUBLIC_INVENTORY_API_URL ?? API_BASE
  ).replace(/\/+$/, "");
}

function isWarehouse(value: unknown): value is Warehouse {
  return value === "LA" || value === "ZGZ";
}

function isProduct(value: unknown): value is InventoryProduct {
  return (
    isObject(value) &&
    typeof value.id === "number" &&
    typeof value.name === "string" &&
    typeof value.sku === "string" &&
    typeof value.client_name === "string" &&
    ["fashion", "electronics", "cosmetics"].includes(String(value.category)) &&
    isWarehouse(value.warehouse) &&
    typeof value.current_stock === "number"
  );
}

function isOrder(value: unknown): value is InventoryOrder {
  return (
    isObject(value) &&
    typeof value.id === "number" &&
    (value.order_type === "inbound" || value.order_type === "outbound") &&
    typeof value.sku_id === "number" &&
    typeof value.quantity === "number" &&
    isWarehouse(value.warehouse) &&
    typeof value.created_at === "string" &&
    typeof value.user_uuid === "string" &&
    isObject(value.sku) &&
    typeof value.sku.id === "number" &&
    typeof value.sku.name === "string" &&
    typeof value.sku.sku === "string" &&
    typeof value.sku.client_name === "string" &&
    typeof value.sku.category === "string" &&
    isWarehouse(value.sku.warehouse)
  );
}

async function inventoryRequest<T>(
  path: string,
  options: RequestInit = {},
  validate?: (value: unknown) => boolean,
): Promise<T> {
  const token = getToken();
  if (!token) {
    redirectToLogin();
    throw new RequestError("Please sign in again to continue.", 401);
  }

  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);

  try {
    const { requestJson } = await import("../../../packages/shared/http");
    return await requestJson<T>(`${getApiBase()}/inventory${path}`, {
      ...options,
      headers,
    }, validate);
  } catch (error) {
    if (error instanceof RequestError && error.status === 401) {
      clearToken();
      redirectToLogin();
    }
    throw error;
  }
}

export function getInventoryProducts(): Promise<InventoryProduct[]> {
  return inventoryRequest(
    "/products",
    {},
    (value) => Array.isArray(value) && value.every(isProduct),
  );
}

export function getInventoryProduct(id: number): Promise<InventoryProduct> {
  return inventoryRequest(`/products/${id}`, {}, isProduct);
}

export function createInventoryProduct(payload: CreateProduct): Promise<InventoryProduct> {
  return inventoryRequest(
    "/products",
    { method: "POST", body: JSON.stringify(payload) },
    isProduct,
  );
}

export function createStockEntry(payload: CreateStockEntry): Promise<StockEntry> {
  return inventoryRequest(
    "/orders/inbound",
    { method: "POST", body: JSON.stringify(payload) },
    (value) =>
      isObject(value) &&
      typeof value.id === "number" &&
      typeof value.sku_id === "number" &&
      typeof value.quantity === "number" &&
      typeof value.reference === "string" &&
      isWarehouse(value.warehouse) &&
      typeof value.created_at === "string" &&
      typeof value.user_uuid === "string",
  );
}

export function createStockExit(payload: CreateStockExit): Promise<StockExit> {
  return inventoryRequest(
    "/orders/outbound",
    { method: "POST", body: JSON.stringify(payload) },
    (value) =>
      isObject(value) &&
      typeof value.id === "number" &&
      typeof value.sku_id === "number" &&
      typeof value.quantity === "number" &&
      (value.exit_type === "dispatch" || value.exit_type === "loss") &&
      (typeof value.tracking_number === "string" || value.tracking_number === null) &&
      isWarehouse(value.warehouse) &&
      typeof value.created_at === "string" &&
      typeof value.user_uuid === "string",
  );
}

export function getInventoryOrders(): Promise<InventoryOrder[]> {
  return inventoryRequest(
    "/orders",
    {},
    (value) => Array.isArray(value) && value.every(isOrder),
  );
}