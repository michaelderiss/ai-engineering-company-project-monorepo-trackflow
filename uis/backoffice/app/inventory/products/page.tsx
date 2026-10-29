"use client";

import { useEffect, useState } from "react";
import InventoryShell from "../../../components/InventoryShell";
import {
  getInventoryProducts,
  type InventoryProduct,
} from "../../../lib/inventory";

function stockLevel(stock: number): "healthy" | "low" | "empty" {
  if (stock === 0) return "empty";
  if (stock < 10) return "low";
  return "healthy";
}

export default function InventoryProductsPage() {
  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    getInventoryProducts()
      .then((data) => { if (active) setProducts(data); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load products.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);

  return (
    <InventoryShell title="Inventory products" currentPath="/inventory/products">
      <section className="inventory-section" aria-labelledby="products-heading" aria-busy={loading}>
        <div className="inventory-toolbar">
          <div>
            <h2 id="products-heading">SKU stock by warehouse</h2>
            <p className="inventory-muted">Stock is calculated from receipts and exits for each SKU location.</p>
          </div>
          <button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)}>
            Refresh stock
          </button>
        </div>

        {loading ? <p role="status">Loading inventory…</p> : error ? (
          <div role="alert" className="inventory-feedback error">
            <p>{error}</p>
            <button type="button" onClick={() => setRevision((value) => value + 1)}>Retry products</button>
          </div>
        ) : products.length === 0 ? <p role="status">No products are registered.</p> : (
          <div className="inventory-table-scroll">
            <table className="inventory-table">
              <caption className="sr-only">TrackFlow products and computed stock by warehouse</caption>
              <thead><tr><th scope="col">Product</th><th scope="col">Client</th><th scope="col">Category</th><th scope="col">Warehouse</th><th scope="col">Current stock</th><th scope="col">Actions</th></tr></thead>
              <tbody>{products.map((product) => (
                <tr key={product.id}>
                  <td><strong>{product.name}</strong><br /><span className="inventory-muted">{product.sku}</span></td>
                  <td>{product.client_name}</td>
                  <td>{product.category}</td>
                  <td>{product.warehouse === "LA" ? "Los Angeles (LA)" : "Zaragoza (ZGZ)"}</td>
                  <td><span className={`inventory-stock ${stockLevel(product.current_stock)}`}>
                    {product.current_stock} {product.current_stock === 1 ? "unit" : "units"}
                  </span></td>
                  <td><div className="table-actions">
                    <a href={`/inventory/orders/inbound?sku_id=${product.id}`}>Receive stock</a>
                    <a href={`/inventory/orders/outbound?sku_id=${product.id}`}>Record exit</a>
                  </div></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
    </InventoryShell>
  );
}