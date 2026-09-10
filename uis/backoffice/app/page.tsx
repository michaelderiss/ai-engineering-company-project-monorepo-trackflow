import { readMilestone2Order } from "../lib/milestone2";

export default function Page() {
  const order = readMilestone2Order();

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">TrackFlow Backoffice</p>
        <h1>Dispatch Planning Console</h1>
        <p>
          This screen imports the latest Milestone 2 dummy-order output and displays the warehouse assignment, carrier
          decision, and delivery assumptions directly.
        </p>
      </header>

      <section className="panel">
        <h2>Milestone 2 Input Snapshot</h2>
        <div className="result-grid">
          <article>
            <h3>Order ID</h3>
            <p>{order.orderId}</p>
          </article>
          <article>
            <h3>Client</h3>
            <p>{order.client}</p>
          </article>
          <article>
            <h3>Destination</h3>
            <p>{order.destination}</p>
          </article>
          <article>
            <h3>Urgency</h3>
            <p>{order.urgency}</p>
          </article>
          <article>
            <h3>Total Weight</h3>
            <p>{order.totalWeight}</p>
          </article>
          <article>
            <h3>Tracking ID</h3>
            <p>{order.trackingId}</p>
          </article>
        </div>
      </section>

      <section className="panel">
        <h2>Imported Dispatch Decision</h2>
        <div className="result-grid">
          <article>
            <h3>Assigned Warehouse</h3>
            <p>{order.assignedWarehouse}</p>
          </article>
          <article>
            <h3>Selected Carrier</h3>
            <p>{order.selectedCarrier}</p>
          </article>
          <article>
            <h3>Expected Delivery Window</h3>
            <p>{order.expectedDeliveryWindow}</p>
          </article>
        </div>
        <p className="note">Warehouse rationale: {order.warehouseReason}</p>
        <p className="note">Carrier rationale: {order.carrierReason}</p>
        <p className="note">CX note: {order.cxNote}</p>
      </section>
    </main>
  );
}
