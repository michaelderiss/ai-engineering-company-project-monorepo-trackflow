"""
Unit test for the sales forecast train/test split.

Validates the 8-year/2-year rule:
  - Training uses the first 8 years (2016-01 to 2023-12)
  - Test uses the last 2 years (2024-01 to 2025-12)
  - No data leakage between the two sets
  - All months total 120 consolidated rows
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# Resolve repo root (tests/pipelines/ -> repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = REPO_ROOT / "data" / "raw" / "trackflow_sales.csv"


@pytest.fixture
def consolidated_data() -> pd.DataFrame:
    """Load consolidated sales data for split testing."""
    df = pd.read_csv(DATA_PATH, parse_dates=["month"])
    df = df[df["market"] == "consolidated"].copy()
    df = df.sort_values("month").reset_index(drop=True)
    return df


class TestSalesForecastSplit:
    """Validate the 8-year / 2-year train/test split."""

    def test_total_months(self, consolidated_data: pd.DataFrame):
        """There must be exactly 120 consolidated months (10 years)."""
        assert len(consolidated_data) == 120, (
            f"Expected 120 months, got {len(consolidated_data)}"
        )

    def test_date_range(self, consolidated_data: pd.DataFrame):
        """Data must span exactly 2016-01 to 2025-12."""
        assert consolidated_data["month"].min() == pd.Timestamp("2016-01-01"), (
            f"Expected start 2016-01-01, got {consolidated_data['month'].min()}"
        )
        assert consolidated_data["month"].max() == pd.Timestamp("2025-12-01"), (
            f"Expected end 2025-12-01, got {consolidated_data['month'].max()}"
        )

    def test_no_missing_months(self, consolidated_data: pd.DataFrame):
        """No months are missing in the 2016-01 to 2025-12 range."""
        date_range = pd.date_range(
            start="2016-01-01", end="2025-12-01", freq="MS"
        )
        actual_months = set(consolidated_data["month"])
        expected_months = set(date_range)
        missing = expected_months - actual_months
        assert len(missing) == 0, (
            f"Missing months: {sorted(missing)}"
        )

    def test_8_year_2_year_split(self, consolidated_data: pd.DataFrame):
        """Training = first 8 years, Test = last 2 years, no overlap."""
        train_end = pd.Timestamp("2024-01-01")  # Exclusive: 2016-01 to 2023-12
        test_start = pd.Timestamp("2024-01-01")  # Inclusive: 2024-01 to 2025-12

        train_mask = consolidated_data["month"] < train_end
        test_mask = consolidated_data["month"] >= test_start

        # Counts
        n_train = train_mask.sum()
        n_test = test_mask.sum()

        assert n_train == 96, (
            f"Expected 96 training months (8 years), got {n_train}"
        )
        assert n_test == 24, (
            f"Expected 24 test months (2 years), got {n_test}"
        )

        # No overlap
        assert not (train_mask & test_mask).any(), (
            "Overlap between training and test sets!"
        )

        # Train + test covers all data
        assert n_train + n_test == len(consolidated_data), (
            f"Train ({n_train}) + Test ({n_test}) != total ({len(consolidated_data)})"
        )

        # Verify no leakage: no training month after test month
        train_months = consolidated_data.loc[train_mask, "month"]
        test_months = consolidated_data.loc[test_mask, "month"]
        assert train_months.max() < test_months.min(), (
            f"Data leakage! Train max {train_months.max()} >= Test min {test_months.min()}"
        )

    def test_all_revenue_positive(self, consolidated_data: pd.DataFrame):
        """All revenue_eur values must be positive."""
        assert (consolidated_data["revenue_eur"] > 0).all(), (
            "Found non-positive revenue_eur values"
        )

    def test_columns_match_briefing(self, consolidated_data: pd.DataFrame):
        """Verify columns match the SFContext.md specification."""
        expected_columns = {
            "month", "revenue_eur", "shipments_processed",
            "avg_revenue_per_shipment_eur", "market",
        }
        actual_columns = set(consolidated_data.columns)
        assert actual_columns == expected_columns, (
            f"Column mismatch. Extra: {actual_columns - expected_columns}, "
            f"Missing: {expected_columns - actual_columns}"
        )