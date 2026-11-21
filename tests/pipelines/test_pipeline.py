"""Unit tests for the business performance pipeline transformation tasks.

Tests use in-memory fixtures shaped like telemetry events — no database
or external API calls. The `compute_kpis` task is tested in isolation
for correct KPI computation and defensive behaviour.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from data.pipelines.pipeline import compute_kpis_logic


# ──────────────────────────────────────────────────────────────
# Helper: build an in-memory DataFrame shaped like extract output
# ──────────────────────────────────────────────────────────────

def _make_event_row(
    event_id: str,
    event_type: str,
    event_timestamp: str,
    warehouse: str,
    client_id: str,
    quantity: int = 0,
) -> dict:
    """Build a single row matching the structure returned by extract_events."""
    properties = {
        "warehouse": warehouse,
        "client_id": client_id,
        "product_id": "SKU-001",
        "product_category": "fashion",
    }
    if quantity is not None:
        properties["quantity"] = quantity
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "properties_json": json.dumps(properties),
    }


def _make_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Convert a list of row dicts into a DataFrame as extract_events would."""
    df = pd.DataFrame(rows)
    if not df.empty:
        df["properties_json"] = df["properties_json"].astype(str)
    return df


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def single_client_single_warehouse() -> pd.DataFrame:
    """3 inbound events + 5 outbound + 1 stockout for one warehouse/client."""
    week = "2026-07-13"
    base_ts = f"{week}T08:00:00Z"
    rows = [
        # 3 inbound events → 2 units each → inbound_units_count = 6
        _make_event_row("e1", "inbound_order_created", base_ts, "los_angeles", "fashion-co", 2),
        _make_event_row("e2", "inbound_order_created", f"{week}T09:00:00Z", "los_angeles", "fashion-co", 2),
        _make_event_row("e3", "inbound_order_created", f"{week}T10:00:00Z", "los_angeles", "fashion-co", 2),
        # 5 outbound orders → outbound_orders_count = 5
        *[_make_event_row(f"o{i}", "outbound_order_created", f"{week}T{i:02d}:00:00Z", "los_angeles", "fashion-co", 1) for i in range(11, 16)],
        # 1 stockout event → stockout_events_count = 1
        _make_event_row("s1", "stock_threshold_triggered", f"{week}T12:00:00Z", "los_angeles", "fashion-co", 0),
        # 2 discrepancy events → discrepancy_events_count = 2
        _make_event_row("d1", "inventory_discrepancy_detected", f"{week}T13:00:00Z", "los_angeles", "fashion-co", 5),
        _make_event_row("d2", "inventory_discrepancy_detected", f"{week}T14:00:00Z", "los_angeles", "fashion-co", 3),
    ]
    return _make_dataframe(rows)


@pytest.fixture
def two_warehouses_two_clients() -> pd.DataFrame:
    """Events spanning two warehouses and two clients."""
    week = "2026-07-20"
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    rows = [
        # LA / fashion-co: 4 inbound units, 2 outbound, 1 stockout, 1 discrepancy
        {"event_id": "e_la_f1", "event_type": "inbound_order_created", "event_timestamp": datetime(2026, 7, 20, 8, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "los_angeles", "client_id": "fashion-co", "quantity": 4})},
        {"event_id": "e_la_f2", "event_type": "outbound_order_created", "event_timestamp": datetime(2026, 7, 20, 9, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "los_angeles", "client_id": "fashion-co", "quantity": 1})},
        {"event_id": "e_la_f3", "event_type": "outbound_order_created", "event_timestamp": datetime(2026, 7, 20, 10, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "los_angeles", "client_id": "fashion-co", "quantity": 1})},
        {"event_id": "e_la_f4", "event_type": "stock_threshold_triggered", "event_timestamp": datetime(2026, 7, 20, 11, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "los_angeles", "client_id": "fashion-co"})},
        {"event_id": "e_la_f5", "event_type": "inventory_discrepancy_detected", "event_timestamp": datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "los_angeles", "client_id": "fashion-co", "system_quantity": 10, "physical_quantity": 8})},
        # ZGZ / purestep_footwear: 10 inbound, 1 outbound, 0 stockout, 0 discrepancy
        {"event_id": "e_zg_p1", "event_type": "inbound_order_created", "event_timestamp": datetime(2026, 7, 20, 8, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "zaragoza", "client_id": "purestep_footwear", "quantity": 10})},
        {"event_id": "e_zg_p2", "event_type": "outbound_order_created", "event_timestamp": datetime(2026, 7, 20, 9, 0, 0, tzinfo=timezone.utc).strftime(fmt), "properties_json": json.dumps({"warehouse": "zaragoza", "client_id": "purestep_footwear", "quantity": 1})},
    ]
    return _make_dataframe(rows)


@pytest.fixture
def empty_df() -> pd.DataFrame:
    """An empty DataFrame (no events extracted)."""
    return pd.DataFrame(columns=["event_id", "event_type", "event_timestamp", "properties_json"])


@pytest.fixture
def malformed_df() -> pd.DataFrame:
    """Events with missing or invalid fields to test defensive behaviour."""
    week = "2026-07-27"
    rows = [
        # Missing warehouse
        {"event_id": "m1", "event_type": "inbound_order_created", "event_timestamp": f"{week}T08:00:00Z", "properties_json": json.dumps({"client_id": "fashion-co", "quantity": 5})},
        # Missing client_id
        {"event_id": "m2", "event_type": "outbound_order_created", "event_timestamp": f"{week}T09:00:00Z", "properties_json": json.dumps({"warehouse": "los_angeles", "quantity": 1})},
        # Null event_timestamp (coerces to NaT)
        {"event_id": "m3", "event_type": "outbound_order_created", "event_timestamp": None, "properties_json": json.dumps({"warehouse": "los_angeles", "client_id": "fashion-co", "quantity": 1})},
        # Non-numeric quantity
        {"event_id": "m4", "event_type": "inbound_order_created", "event_timestamp": f"{week}T10:00:00Z", "properties_json": json.dumps({"warehouse": "zaragoza", "client_id": "purestep_footwear", "quantity": "abc"})},
        # Valid row — should remain
        {"event_id": "m5", "event_type": "inbound_order_created", "event_timestamp": f"{week}T11:00:00Z", "properties_json": json.dumps({"warehouse": "zaragoza", "client_id": "purestep_footwear", "quantity": 3})},
        # Valid outbound for discrepancy rate test
        {"event_id": "m6", "event_type": "outbound_order_created", "event_timestamp": f"{week}T12:00:00Z", "properties_json": json.dumps({"warehouse": "zaragoza", "client_id": "purestep_footwear", "quantity": 1})},
        # inventory_discrepancy_detected with no quantity field
        {"event_id": "m7", "event_type": "inventory_discrepancy_detected", "event_timestamp": f"{week}T13:00:00Z", "properties_json": json.dumps({"warehouse": "zaragoza", "client_id": "purestep_footwear"})},
    ]
    return _make_dataframe(rows)


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════

class TestComputeKpis:
    """Tests for the compute_kpis transformation task."""

    def test_hand_computed_kpis(self, single_client_single_warehouse: pd.DataFrame):
        """Verify computed KPIs match hand-calculated values for known input.

        For los_angeles / fashion-co / 2026-07-13:
          - inbound_order_created × 3 events × 2 qty each = inbound_units_count = 6
          - outbound_order_created × 5 events = outbound_orders_count = 5
          - stock_threshold_triggered × 1 event = stockout_events_count = 1
          - inventory_discrepancy_detected × 2 events = discrepancy_events_count = 2
          - discrepancy_rate = 2 / 5 = 0.4
        """
        results = compute_kpis_logic(single_client_single_warehouse)

        assert len(results) == 1, "Expected exactly one KPI row"

        row = results[0]
        assert row["warehouse"] == "los_angeles"
        assert row["client_id"] == "fashion-co"
        assert row["week_start"] == "2026-07-13"
        assert row["inbound_units_count"] == 6
        assert row["outbound_orders_count"] == 5
        assert row["stockout_events_count"] == 1
        assert row["discrepancy_events_count"] == 2
        # discrepancy_rate = discrepancy / outbound = 2 / 5 = 0.4
        assert row["discrepancy_rate"] == pytest.approx(0.4), \
            f"Expected discrepancy_rate=0.4, got {row['discrepancy_rate']}"

    def test_zero_outbound_gives_zero_discrepancy_rate(self):
        """When there are no outbound orders, discrepancy_rate must be 0.0."""
        week = "2026-08-03"
        rows = [
            _make_event_row("e1", "inbound_order_created", f"{week}T08:00:00Z", "los_angeles", "fashion-co", 5),
            # 2 discrepancy events but 0 outbound orders
            _make_event_row("d1", "inventory_discrepancy_detected", f"{week}T09:00:00Z", "los_angeles", "fashion-co"),
            _make_event_row("d2", "inventory_discrepancy_detected", f"{week}T10:00:00Z", "los_angeles", "fashion-co"),
        ]
        df = _make_dataframe(rows)
        results = compute_kpis_logic(df)

        assert len(results) == 1
        row = results[0]
        assert row["outbound_orders_count"] == 0
        assert row["discrepancy_events_count"] == 2
        # Should be 0.0 (not NaN, not infinity)
        assert row["discrepancy_rate"] == 0.0

    def test_multiple_warehouses_and_clients(self, two_warehouses_two_clients: pd.DataFrame):
        """Verify correct KPI computation across two warehouses and two clients."""
        results = compute_kpis_logic(two_warehouses_two_clients)

        assert len(results) == 2, "Expected exactly 2 KPI rows (LA/fashion-co, ZGZ/purestep_footwear)"

        # Build index for lookup
        idx = {(r["warehouse"], r["client_id"]): r for r in results}

        # LA / fashion-co
        la_row = idx.get(("los_angeles", "fashion-co"))
        assert la_row is not None, "Missing LA/fashion-co KPI row"
        assert la_row["inbound_units_count"] == 4
        assert la_row["outbound_orders_count"] == 2
        assert la_row["stockout_events_count"] == 1
        assert la_row["discrepancy_events_count"] == 1
        assert la_row["discrepancy_rate"] == pytest.approx(1.0 / 2.0), \
            f"Expected discrepancy_rate=0.5, got {la_row['discrepancy_rate']}"

        # ZGZ / purestep_footwear
        zg_row = idx.get(("zaragoza", "purestep_footwear"))
        assert zg_row is not None, "Missing ZGZ/purestep_footwear KPI row"
        assert zg_row["inbound_units_count"] == 10
        assert zg_row["outbound_orders_count"] == 1
        assert zg_row["stockout_events_count"] == 0
        assert zg_row["discrepancy_events_count"] == 0
        assert zg_row["discrepancy_rate"] == 0.0

    def test_empty_input_returns_empty(self, empty_df: pd.DataFrame):
        """Empty input must return an empty list without errors."""
        results = compute_kpis_logic(empty_df)
        assert results == []

    def test_malformed_input_defensive(self, malformed_df: pd.DataFrame):
        """Verify defensive behaviour against invalid/malformed input.

        The malformed fixture has:
          - 1 row missing warehouse (dropped)
          - 1 row missing client_id (dropped)
          - 1 row with null timestamp (dropped at NaT filtering)
          - 1 row with non-numeric quantity (coerced to 0)
          - 2 valid rows for zaragoza/purestep_footwear
          - 1 discrepancy with no quantity (counted as is)
        After defensive filtering, only the zaragoza/purestep_footwear rows remain.
        """
        results = compute_kpis_logic(malformed_df)

        # Only the zaragoza/purestep_footwear rows have both warehouse and client_id
        assert len(results) == 1, (
            f"Expected 1 KPI row after defensive filtering, got {len(results)}"
        )
        row = results[0]
        assert row["warehouse"] == "zaragoza"
        assert row["client_id"] == "purestep_footwear"
        # Valid inbound: 1 row × 3 qty + 1 row with "abc" coerced to 0 = 3
        # But wait - the "abc" row has warehouse=zaragoza, client_id=purestep_footwear
        # so it is included but quantity coerced to 0
        assert row["inbound_units_count"] == 3, (
            f"Expected inbound_units_count=3 (3 from m5 + 0 from m4 coercion), "
            f"got {row['inbound_units_count']}"
        )
        # Valid outbound: 1 event
        assert row["outbound_orders_count"] == 1
        # No stockout
        assert row["stockout_events_count"] == 0
        # 1 discrepancy event
        assert row["discrepancy_events_count"] == 1
        # discrepancy_rate = 1 / 1 = 1.0
        assert row["discrepancy_rate"] == pytest.approx(1.0)