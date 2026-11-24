"""Unit tests for train/test split and temporal CV order."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.train_sales_forecast import (  # noqa: E402
    engineer_features,
    load_data,
    make_temporal_cv_splits,
    split_data,
)


def test_eight_year_two_year_split():
    features = engineer_features(load_data())
    train, test = split_data(features)
    assert len(train) == 84
    assert len(test) == 24
    assert train["month"].min() == pd.Timestamp("2017-01-01")
    assert train["month"].max() == pd.Timestamp("2023-12-01")
    assert test["month"].min() == pd.Timestamp("2024-01-01")
    assert test["month"].max() == pd.Timestamp("2025-12-01")
    assert train["month"].max() < test["month"].min()


def test_temporal_cv_preserves_chronology_and_expanding_windows():
    features = engineer_features(load_data())
    train, _ = split_data(features)
    folds = make_temporal_cv_splits(train)

    assert len(folds) == 5
    prior_validation_max = -1
    previous_train_size = 0
    for train_indices, validation_indices in folds:
        assert train_indices.max() < validation_indices.min()
        assert train_indices[0] == 0
        assert len(train_indices) > previous_train_size
        assert validation_indices.min() > prior_validation_max
        assert len(validation_indices) == 12
        previous_train_size = len(train_indices)
        prior_validation_max = validation_indices.max()


def test_causal_features_at_validation_boundary_use_only_past_rows():
    raw = load_data()
    features = engineer_features(raw)
    train, _ = split_data(features)
    folds = make_temporal_cv_splits(train)

    for _, validation_indices in folds:
        first_validation = train.iloc[validation_indices[0]]
        position = int(raw.index[raw["month"].eq(first_validation["month"])][0])
        assert first_validation["revenue_lag_1"] == raw.loc[position - 1, "revenue_eur"]
        assert first_validation["revenue_lag_12"] == raw.loc[position - 12, "revenue_eur"]
        assert abs(first_validation["revenue_ma_3"] - raw.loc[position - 3:position - 1, "revenue_eur"].mean()) < 1e-8
