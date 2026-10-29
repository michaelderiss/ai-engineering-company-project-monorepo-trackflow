import type { ReactNode } from "react";

const NAV_ITEMS = [
  { label: "Products", href: "/inventory/products" },
  { label: "Inbound", href: "/inventory/orders/inbound" },
  { label: "Outbound", href: "/inventory/orders/outbound" },
  { label: "Order history", href: "/inventory/orders" },
];

export default function InventoryShell({
  title,
  currentPath,
  children,
}: {
  title: string;
  currentPath: string;
  children: ReactNode;
}) {
  return (
    <main className="inventory-shell">
      <header className="inventory-header">
        <div>
          <p className="inventory-eyebrow">Warehouse operations</p>
          <h1>{title}</h1>
        </div>
        <a className="text-link" href="/">Operations Home</a>
      </header>
      <nav className="inventory-nav" aria-label="Inventory pages">
        {NAV_ITEMS.map((item) => (
          <a
            key={item.href}
            href={item.href}
            aria-current={currentPath === item.href ? "page" : undefined}
          >
            {item.label}
          </a>
        ))}
      </nav>
      {children}
    </main>
  );
}