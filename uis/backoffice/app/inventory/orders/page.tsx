"use client";

import { useEffect, useState } from "react";
import InventoryShell from "../../../components/InventoryShell";
import {
  getInventoryOrders,
  type InventoryOrder,
} from "../../../lib/inventory";

function movementLabel(order: InventoryOrder): string {
  if (order.order_type === "inbound") return "Inbound receipt";
  return order.exit_type === "loss" ? "Confirmed loss" : "Customer dispatch";
}

export default function InventoryOrdersPage() {
  const [orders, setOrders] = useState<InventoryOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    getInventoryOrders()
      .then((data) => { if (active) setOrders(data); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load order history.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);

  return (
    <InventoryShell title="Inventory order history" currentPath="/inventory/orders">
      <section className="inventory-section" aria-labelledby="orders-heading" aria-busy={loading}>
        <div className="inventory-toolbar">
          <div>
            <h2 id="orders-heading">Stock movements</h2>
            <p className="inventory-muted">Read-only history of receipts, dispatches, and confirmed losses.</p>
          </div>
          <button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)}>
            Refresh history
          </button>
        </div>
        {loading ? <p role="status">Loading order history…</p> : error ? (
          <div role="alert" className="inventory-feedback error"><p>{error}</p><button type="button" onClick={() => setRevision((value) => value + 1)}>Retry history</button></div>
        ) : orders.length === 0 ? <p role="status">No stock movements have been recorded.</p> : (
          <div className="inventory-table-scroll">
            <table className="inventory-table">
              <caption className="sr-only">Inventory movement history with product and creator</caption>
              <thead><tr><th scope="col">Product</th><th scope="col">Movement</th><th scope="col">Quantity</th><th scope="col">Warehouse</th><th scope="col">Reference / tracking</th><th scope="col">Created</th><th scope="col">Created by</th></tr></thead>
              <tbody>{orders.map((order) => (
                <tr key={`${order.order_type}-${order.id}`}>
                  <td><strong>{order.sku.name}</strong><br /><span className="inventory-muted">{order.sku.sku}</span></td>
                  <td><span className={`inventory-type ${order.order_type}`}>{movementLabel(order)}</span></td>
                  <td>{order.quantity}</td>
                  <td>{order.warehouse === "LA" ? "Los Angeles (LA)" : "Zaragoza (ZGZ)"}</td>
                  <td>{order.reference ?? order.tracking_number ?? "—"}</td>
                  <td><time dateTime={order.created_at}>{new Date(order.created_at).toLocaleString()}</time></td>
                  <td>{order.user_uuid}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
    </InventoryShell>
  );
}