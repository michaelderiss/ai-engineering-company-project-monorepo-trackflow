"use client";

import { type FormEvent, useEffect, useState } from "react";
import InventoryShell from "../../../../components/InventoryShell";
import {
  createStockEntry,
  getInventoryProducts,
  type InventoryProduct,
} from "../../../../lib/inventory";

export default function InboundOrderPage() {
  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [skuId, setSkuId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reference, setReference] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const requestedSku = new URLSearchParams(window.location.search).get("sku_id");
    if (requestedSku && /^\d+$/.test(requestedSku)) setSkuId(requestedSku);
  }, []);

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

  const selectedProduct = products.find((product) => product.id === Number(skuId));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProduct || submitting) return;
    const parsedQuantity = Number(quantity);
    if (!Number.isInteger(parsedQuantity) || parsedQuantity <= 0 || !reference.trim()) {
      setError("Choose a product, enter a positive whole quantity, and provide a reference.");
      return;
    }

    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const entry = await createStockEntry({
        sku_id: selectedProduct.id,
        quantity: parsedQuantity,
        reference: reference.trim(),
        warehouse: selectedProduct.warehouse,
      });
      setSuccess(`Receipt #${entry.id} recorded for ${selectedProduct.name}.`);
      setSkuId("");
      setQuantity("");
      setReference("");
      setRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not record this receipt.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <InventoryShell title="Inbound receipt" currentPath="/inventory/orders/inbound">
      <section className="inventory-section inventory-form" aria-labelledby="inbound-heading">
        <h2 id="inbound-heading">Receive client stock</h2>
        <p className="inventory-muted">Record goods received at the selected SKU’s warehouse.</p>
        {loading ? <p role="status">Loading products…</p> : error && products.length === 0 ? (
          <div role="alert" className="inventory-feedback error"><p>{error}</p><button type="button" onClick={() => setRevision((value) => value + 1)}>Retry products</button></div>
        ) : products.length === 0 ? <p role="status">No products are available for a receipt.</p> : (
          <form className="stack" onSubmit={submit} aria-busy={submitting}>
            <fieldset className="incident-fields" disabled={submitting || loading}>
              <label htmlFor="inbound-product">Product <span className="required">*</span>
                <select id="inbound-product" className="selector" required value={skuId} onChange={(event) => setSkuId(event.target.value)}>
                  <option value="">Select a product</option>
                  {products.map((product) => <option key={product.id} value={product.id}>
                    {product.name} — {product.sku} ({product.warehouse})
                  </option>)}
                </select>
              </label>
              <div className="form-grid">
                <label htmlFor="inbound-quantity">Quantity <span className="required">*</span>
                  <input id="inbound-quantity" className="text-input" type="number" min="1" step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} />
                </label>
                <label htmlFor="inbound-reference">Client reference <span className="required">*</span>
                  <input id="inbound-reference" className="text-input" type="text" maxLength={120} required value={reference} onChange={(event) => setReference(event.target.value)} placeholder="e.g. PO-2024-0098" />
                </label>
              </div>
              {selectedProduct && <p className="inventory-stock-preview">
                <span>Receiving warehouse</span>
                <strong>{selectedProduct.warehouse === "LA" ? "Los Angeles (LA)" : "Zaragoza (ZGZ)"}</strong>
              </p>}
              <div className="actions"><button type="submit" disabled={!selectedProduct || submitting}>
                {submitting ? "Recording receipt…" : "Record inbound receipt"}
              </button></div>
            </fieldset>
            {error && <p role="alert" className="inventory-feedback error">{error}</p>}
            {success && <p role="status" className="inventory-feedback success">{success}</p>}
          </form>
        )}
      </section>
    </InventoryShell>
  );
}