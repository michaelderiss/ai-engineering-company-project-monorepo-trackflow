"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import InventoryShell from "../../../components/InventoryShell";
import {
  getInventoryOrders,
  type InventoryOrder,
} from "../../../lib/inventory";

const InventoryHistoryTable = dynamic(() => import("../../../components/InventoryHistoryTable"), {
  ssr: false,
  loading: () => <p role="status">Loading movement table...</p>,
});

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
          <InventoryHistoryTable orders={orders} />
        )}
      </section>
    </InventoryShell>
  );
}