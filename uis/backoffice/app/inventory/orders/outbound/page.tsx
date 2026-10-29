"use client";

import { type FormEvent, useEffect, useState } from "react";
import InventoryShell from "../../../../components/InventoryShell";
import {
  createStockExit,
  getInventoryProduct,
  getInventoryProducts,
  type ExitType,
  type InventoryProduct,
} from "../../../../lib/inventory";

export default function OutboundOrderPage() {
  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [skuId, setSkuId] = useState("");
  const [selectedProduct, setSelectedProduct] = useState<InventoryProduct | null>(null);
  const [stockRevision, setStockRevision] = useState(0);
  const [stockLoading, setStockLoading] = useState(false);
  const [stockError, setStockError] = useState("");
  const [quantity, setQuantity] = useState("");
  const [exitType, setExitType] = useState<ExitType>("dispatch");
  const [trackingNumber, setTrackingNumber] = useState("");
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

  useEffect(() => {
    let active = true;
    if (!skuId) {
      setSelectedProduct(null);
      setStockError("");
      setStockLoading(false);
      return () => { active = false; };
    }

    setStockLoading(true);
    setStockError("");
    getInventoryProduct(Number(skuId))
      .then((product) => { if (active) setSelectedProduct(product); })
      .catch((reason: unknown) => {
        if (active) {
          setSelectedProduct(null);
          setStockError(reason instanceof Error ? reason.message : "Could not load current stock.");
        }
      })
      .finally(() => { if (active) setStockLoading(false); });
    return () => { active = false; };
  }, [skuId, stockRevision]);

  const parsedQuantity = Number(quantity);
  const exceedsStock = Boolean(
    selectedProduct && Number.isInteger(parsedQuantity) &&
    parsedQuantity > selectedProduct.current_stock,
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProduct || submitting || stockLoading) return;
    if (!Number.isInteger(parsedQuantity) || parsedQuantity <= 0) {
      setError("Enter a positive whole quantity.");
      return;
    }
    if (exitType === "dispatch" && !trackingNumber.trim()) {
      setError("A tracking number is required for a customer dispatch.");
      return;
    }

    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const created = await createStockExit({
        sku_id: selectedProduct.id,
        quantity: parsedQuantity,
        exit_type: exitType,
        tracking_number: exitType === "dispatch" ? trackingNumber.trim() : null,
        warehouse: selectedProduct.warehouse,
      });
      setSuccess(`Exit #${created.id} recorded for ${selectedProduct.name}.`);
      setQuantity("");
      setTrackingNumber("");
      const refreshed = await getInventoryProduct(selectedProduct.id);
      setSelectedProduct(refreshed);
      setRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not record this stock exit.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <InventoryShell title="Outbound order" currentPath="/inventory/orders/outbound">
      <section className="inventory-section inventory-form" aria-labelledby="outbound-heading">
        <h2 id="outbound-heading">Dispatch or write off stock</h2>
        <p className="inventory-muted">Available stock is refreshed when you select a product. The API performs the final stock check.</p>
        {loading ? <p role="status">Loading products…</p> : error && products.length === 0 ? (
          <div role="alert" className="inventory-feedback error"><p>{error}</p><button type="button" onClick={() => setRevision((value) => value + 1)}>Retry products</button></div>
        ) : products.length === 0 ? <p role="status">No products are available for an outbound order.</p> : (
          <form className="stack" onSubmit={submit} aria-busy={submitting}>
            <fieldset className="incident-fields" disabled={submitting || loading}>
              <label htmlFor="outbound-product">Product <span className="required">*</span>
                <select id="outbound-product" className="selector" required value={skuId} onChange={(event) => {
                  setSkuId(event.target.value);
                  setQuantity("");
                  setError("");
                  setSuccess("");
                }}>
                  <option value="">Select a product</option>
                  {products.map((product) => <option key={product.id} value={product.id}>
                    {product.name} — {product.sku} ({product.warehouse})
                  </option>)}
                </select>
              </label>

              {stockLoading ? <p role="status">Refreshing available stock…</p> : stockError ? (
                <div role="alert" className="inventory-feedback error"><p>{stockError}</p><button type="button" onClick={() => setStockRevision((value) => value + 1)}>Retry stock</button></div>
              ) : selectedProduct && <div className="inventory-stock-preview" role="status">
                <span>Available at {selectedProduct.warehouse === "LA" ? "Los Angeles (LA)" : "Zaragoza (ZGZ)"}</span>
                <strong>{selectedProduct.current_stock} {selectedProduct.current_stock === 1 ? "unit" : "units"}</strong>
              </div>}

              <div className="form-grid">
                <label htmlFor="outbound-quantity">Quantity <span className="required">*</span>
                  <input id="outbound-quantity" className="text-input" type="number" min="1" step="1" required disabled={!selectedProduct || stockLoading || !!stockError} value={quantity} onChange={(event) => setQuantity(event.target.value)} />
                </label>
                <label htmlFor="outbound-type">Exit type <span className="required">*</span>
                  <select id="outbound-type" className="selector" value={exitType} onChange={(event) => {
                    const nextType = event.target.value as ExitType;
                    setExitType(nextType);
                    if (nextType === "loss") setTrackingNumber("");
                    setError("");
                  }}>
                    <option value="dispatch">Customer dispatch</option>
                    <option value="loss">Confirmed loss</option>
                  </select>
                </label>
              </div>

              {exitType === "dispatch" && <label htmlFor="outbound-tracking">Tracking number <span className="required">*</span>
                <input id="outbound-tracking" className="text-input" type="text" maxLength={120} required value={trackingNumber} onChange={(event) => setTrackingNumber(event.target.value)} />
              </label>}

              {exceedsStock && <p role="alert" className="inventory-warning">
                Requested quantity exceeds available stock ({selectedProduct?.current_stock}). The API will reject this exit.
              </p>}
              <div className="actions"><button type="submit" disabled={!selectedProduct || stockLoading || !!stockError || submitting}>
                {submitting ? "Recording exit…" : exitType === "dispatch" ? "Record dispatch" : "Record loss"}
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