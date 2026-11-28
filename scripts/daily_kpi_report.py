#!/usr/bin/env python3
"""
Daily KPI Report — generate a compact JSON summary of today's business KPIs
for CEO/operations leadership.

Usage:
    python scripts/daily_kpi_report.py                          # print to stdout
    python scripts/daily_kpi_report.py --output report.json     # write to file
    python scripts/daily_kpi_report.py --warehouse WH1          # filter one warehouse

Relies on the reporting_daily_kpis table being populated by the pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from typing import Any

import psycopg2
import psycopg2.extras

DATABASE_URL_ENV = "REPORTING_DATABASE_URL"
DEFAULT_DAYS = 7  # look back up to 7 days


def get_connection() -> psycopg2.extensions.connection:
    """Return a database connection using the configured DATABASE_URL."""
    db_url = os.environ.get(DATABASE_URL_ENV)
    if not db_url:
        print(
            f"❌ {DATABASE_URL_ENV} environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)
    return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_kpis(
    conn: psycopg2.extensions.connection,
    *,
    warehouse: str | None = None,
    since: date | None = None,
) -> list[dict[str, Any]]:
    """Return KPI rows, optionally filtered by warehouse and recency."""
    conditions: list[str] = []
    params: list[Any] = []

    if warehouse:
        conditions.append("warehouse_id = %s")
        params.append(warehouse)

    if since:
        conditions.append("kpi_date >= %s")
        params.append(since)

    where = " AND ".join(conditions) if conditions else "TRUE"

    query = f"""
        SELECT
            kpi_date,
            warehouse_id,
            client_id,
            inbound_volume,
            outbound_throughput,
            stockout_frequency,
            discrepancy_count,
            discrepancy_rate,
            updated_at
        FROM reporting_daily_kpis
        WHERE {where}
        ORDER BY kpi_date DESC, warehouse_id, client_id
    """
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]  # RealDict → plain dict


def format_kpi_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw DB row to a JSON-friendly dict with serialised dates."""
    return {
        "date": str(row["kpi_date"]),
        "warehouse": row["warehouse_id"],
        "client": row["client_id"],
        "inbound_volume": row["inbound_volume"],
        "outbound_throughput": row["outbound_throughput"],
        "stockout_frequency": row["stockout_frequency"],
        "discrepancy_count": row["discrepancy_count"],
        "discrepancy_rate": round(float(row["discrepancy_rate"]), 4),
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def build_report(
    rows: list[dict[str, Any]],
    *,
    summary: bool = True,
) -> dict[str, Any]:
    """Build a report dict with optional summary section."""
    report: dict[str, Any] = {
        "generated_at": date.today().isoformat(),
        "record_count": len(rows),
        "entries": [format_kpi_row(r) for r in rows],
    }

    if summary and rows:
        warehouses = sorted({r["warehouse_id"] for r in rows})
        clients = sorted({r["client_id"] for r in rows})
        dates = sorted({r["kpi_date"] for r in rows}, reverse=True)

        # Aggregate totals
        total_inbound = sum(r["inbound_volume"] or 0 for r in rows)
        total_outbound = sum(r["outbound_throughput"] or 0 for r in rows)
        total_stockouts = sum(r["stockout_frequency"] or 0 for r in rows)
        total_discrepancy = sum(r["discrepancy_count"] or 0 for r in rows)

        avg_rates = [
            r["discrepancy_rate"]
            for r in rows
            if r["discrepancy_rate"] is not None
        ]
        avg_discrepancy_rate = (
            round(sum(avg_rates) / len(avg_rates), 4) if avg_rates else None
        )

        report["summary"] = {
            "warehouses": warehouses,
            "clients": clients,
            "date_range": f"{dates[-1]}..{dates[0]}" if len(dates) > 1 else dates[0],
            "total_inbound_volume": total_inbound,
            "total_outbound_throughput": total_outbound,
            "total_stockout_frequency": total_stockouts,
            "total_discrepancy_count": total_discrepancy,
            "avg_discrepancy_rate": avg_discrepancy_rate,
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a daily KPI report from the pipeline's output table.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Path to write the JSON report (default: stdout).",
    )
    parser.add_argument(
        "--warehouse",
        "-w",
        type=str,
        help="Filter results to a single warehouse ID.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"How many days to look back (default: {DEFAULT_DAYS}).",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Omit the summary section from the report.",
    )
    args = parser.parse_args()

    since = date.today() - timedelta(days=args.days) if args.days else None

    conn = get_connection()
    try:
        rows = fetch_kpis(conn, warehouse=args.warehouse, since=since)
        report = build_report(rows, summary=not args.no_summary)
    finally:
        conn.close()

    report_json = json.dumps(report, indent=2, default=str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"✅ Report written to {args.output}  ({len(rows)} rows)", file=sys.stderr)
    else:
        print(report_json)


if __name__ == "__main__":
    main()