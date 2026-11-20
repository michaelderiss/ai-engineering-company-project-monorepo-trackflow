"""Reproducible load experiment; all storage is created and deleted in /tmp."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def seed_load(engine, incident_store, products: int, incidents: int):
    from sqlalchemy import insert
    from services.api.inventory_models import SKU, StockEntry, StockExit
    from packages.shared.incidents import BRANCHES, CATEGORIES, ORIGINS, STATUSES

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with engine.begin() as db:
        db.execute(insert(SKU), [
            {"id": 1000 + index, "name": f"{('Sneaker', 'Earbuds', 'Serum')[index % 3]} variant {index}",
             "sku": f"LOAD-{index:06d}", "client_name": f"Brand {index % 40}",
             "category": ("fashion", "electronics", "cosmetics")[index % 3],
             "warehouse": "LA" if index % 2 else "ZGZ"}
            for index in range(products)
        ])
        for model, outbound in ((StockEntry, False), (StockExit, True)):
            rows = []
            for index in range(products):
                for receipt in range(10):
                    row = {"sku_id": 1000 + index, "quantity": 1 + index % 5 if outbound else 20 + index % 30,
                           "warehouse": "LA" if index % 2 else "ZGZ",
                           "created_at": start + timedelta(days=receipt, minutes=index % 1440),
                           "user_uuid": str(1 + index % 15)}
                    if outbound:
                        row.update(exit_type="loss" if receipt % 4 == 0 else "dispatch",
                                   tracking_number=None if receipt % 4 == 0 else f"LOAD-{index}-{receipt}")
                    else:
                        row["reference"] = f"PO-{index % 40}-{index}-{receipt}"
                    rows.append(row)
            db.execute(insert(model), rows)
    with incident_store.connection() as db:
        db.executemany(
            "INSERT INTO incidents (title, description, category, status, origin, branch, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(f"Carrier delay {index}", f"Synthetic route {index % 200}; parcel {index}",
              list(CATEGORIES)[index % len(CATEGORIES)], list(STATUSES)[index % len(STATUSES)],
              list(ORIGINS)[index % len(ORIGINS)], list(BRANCHES)[index % len(BRANCHES)],
              (start + timedelta(minutes=index)).isoformat(), (start + timedelta(minutes=index)).isoformat())
             for index in range(incidents)],
        )


def measure(client, path, headers, repeats):
    durations = []
    size = 0
    for _ in range(repeats):
        start = perf_counter()
        response = client.get(path, headers=headers)
        durations.append((perf_counter() - start) * 1000)
        response.raise_for_status()
        size = len(response.content)
    return {"requests": repeats, "median_ms": round(median(durations), 3),
            "max_ms": round(max(durations), 3), "first_ms": round(durations[0], 3), "bytes": size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--products", type=int, default=2000)
    parser.add_argument("--incidents", type=int, default=20000)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--uncached", action="store_true", help="Bypass both caches for a comparable baseline")
    args = parser.parse_args()
    if min(args.products, args.incidents, args.repeats) < 1:
        parser.error("counts must be positive")
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with TemporaryDirectory(prefix="trackflow-profile-") as directory:
        storage = Path(directory)
        os.environ["DATABASE_URL"] = f"sqlite:///{storage / 'inventory.sqlite3'}"
        from fastapi.testclient import TestClient
        from services.api import database, incidents, inventory_database
        from services.api.auth import create_access_token
        from services.api.cache import catalog_cache, summary_cache
        from services.api.main import app
        from services.api.models import UserCreate

        if args.uncached:
            for cache in (catalog_cache, summary_cache):
                cache.get_or_load = lambda key, loader: loader()
        database.USER_DB_PATH = storage / "users.json"
        database.DB_PATH = storage / "suppliers.json"
        incidents.DB_PATH = storage / "incidents.sqlite3"
        paths = ("/inventory/products", "/api/incidents/summary")
        try:
            with TestClient(app) as client:
                account = database.create_user(UserCreate(email="profile@trackflow.test", password="SyntheticOnly123!"))
                headers = {"Authorization": f"Bearer {create_access_token({'sub': str(account.id)})}"}
                result = {"environment": "temporary SQLite / TestClient; not production telemetry",
                          "rows_before": {"products": 6, "entries": 4, "exits": 3, "incidents": 0},
                          "before_seed": {path: measure(client, path, headers, args.repeats) for path in paths}}
                seed_load(inventory_database.engine, incidents, args.products, args.incidents)
                catalog_cache.clear()
                summary_cache.clear()
                result["rows_after"] = {"products": args.products + 6, "entries": args.products * 10 + 4,
                                        "exits": args.products * 10 + 3, "incidents": args.incidents}
                result["after_seed"] = {path: measure(client, path, headers, args.repeats) for path in paths}
                result["endpoints"] = [{"path": route.path, "methods": sorted(route.methods)}
                                       for route in app.routes if hasattr(route, "methods")]
                print(json.dumps(result, indent=2))
        finally:
            inventory_database.engine.dispose()


if __name__ == "__main__":
    main()