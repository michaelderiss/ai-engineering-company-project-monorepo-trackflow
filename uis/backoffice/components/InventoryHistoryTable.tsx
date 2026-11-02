"use client";

import { useMemo, useState } from "react";
import type { InventoryOrder } from "../lib/inventory";

const PAGE_SIZE = 50;

export default function InventoryHistoryTable({ orders }: { orders: InventoryOrder[] }) {
  const [page, setPage] = useState(0);
  const rows = useMemo(() => orders.map((order) => ({
    ...order,
    movement: order.order_type === "inbound" ? "Inbound receipt" : order.exit_type === "loss" ? "Confirmed loss" : "Customer dispatch",
    createdLabel: new Date(order.created_at).toLocaleString(),
    warehouseLabel: order.warehouse === "LA" ? "Los Angeles (LA)" : "Zaragoza (ZGZ)",
  })), [orders]);
  const lastPage = Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1);
  const currentPage = Math.min(page, lastPage);
  const visibleRows = rows.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  return (
    <>
      <div className="inventory-table-scroll">
        <table className="inventory-table">
          <caption className="sr-only">Inventory movement history with product and creator</caption>
          <thead><tr><th scope="col">Product</th><th scope="col">Movement</th><th scope="col">Quantity</th><th scope="col">Warehouse</th><th scope="col">Reference / tracking</th><th scope="col">Created</th><th scope="col">Created by</th></tr></thead>
          <tbody>{visibleRows.map((order) => (
            <tr key={`${order.order_type}-${order.id}`}>
              <td><strong>{order.sku.name}</strong><br /><span className="inventory-muted">{order.sku.sku}</span></td>
              <td><span className={`inventory-type ${order.order_type}`}>{order.movement}</span></td>
              <td>{order.quantity}</td>
              <td>{order.warehouseLabel}</td>
              <td>{order.reference ?? order.tracking_number ?? "—"}</td>
              <td><time dateTime={order.created_at}>{order.createdLabel}</time></td>
              <td>{order.user_uuid}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <nav className="inventory-toolbar" aria-label="Movement history pages">
        <button type="button" aria-label="Previous history page" title="Previous history page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>←</button>
        <p role="status">Page {currentPage + 1} of {lastPage + 1} · {rows.length} movements</p>
        <button type="button" aria-label="Next history page" title="Next history page" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>→</button>
      </nav>
    </>
  );
}