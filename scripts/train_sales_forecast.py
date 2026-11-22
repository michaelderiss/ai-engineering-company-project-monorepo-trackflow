"""
TrackFlow Sales Forecasting Model
==================================
Train a regression model to predict monthly revenue_eur (consolidated)
using 8 years of training data and evaluate on 2 years of test data.

Algorithm choice: Random Forest (scikit-learn)
------------------------------------------------
Rationale for choosing Random Forest over XGBoost:
1. Explainability: Thomas (CEO) and Ana (Warehouse) need to understand
   and trust the model before committing to a full executive dashboard.
   Random Forest averages many independent trees - easier to explain to
   non-technical stakeholders than XGBoost's sequential boosting approach.

2. Data size: With only 96 training samples (monthly data), XGBoost's
   sequential correction process risks overfitting more quickly and
   requires careful tuning of learning rate, tree depth, and
   regularization. Random Forest with moderate tree count generalizes
   better on small tabular data out of the box.

3. Stakeholder context: Finance is asking about feasibility, not
   demanding maximum accuracy. A Random Forest model with sensible
   defaults gives us a reliable baseline. If Finance later needs the
   extra few percent of accuracy, we can invest tuning time in XGBoost.

Metrics reported: MSE, PSI, Gini, K2 Score
---------------------------------------------
- MSE (Mean Squared Error): Average squared difference between predicted
  and actual revenue. Reported in EUR^2 and as % of average monthly
  revenue. A low MSE alone isn't enough because it doesn't tell us
  whether the model distinguishes high-season from low-season months
  (that's what Gini captures) or whether the revenue distribution shifted
  in the test period (that's what PSI captures).

- PSI (Population Stability Index): Measures whether the distribution of
  predictions has shifted relative to the actual values between training
  and test. PSI > 0.25 signals significant shift - may indicate that
  market conditions or operational mix changed.

- Gini coefficient: Measures the model's ability to rank months by
  revenue correctly (like AUC for regression). High Gini means Thomas
  can confidently distinguish a normal low-season month from an
  atypical drop.

- K2 Score (Kuiper's K2 statistic): A variant of the Kolmogorov-Smirnov
  test that is sensitive to differences in both the location and shape
  of the predicted vs actual distribution (especially tail behaviour).
  Lower values indicate the model captures the full distribution shape.

Author: TrackFlow AI Engineering
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message="X has feature names")

# Configuration
RANDOM_SEED = 42
TRAIN_YEARS = 8
TEST_YEARS = 2

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "raw" / "trackflow_sales.csv"
OUTPUT_DIR = REPO_ROOT / "scripts"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_data(path):
    """Load the consolidated sales data."""
    df = pd.read_csv(path, parse_dates=["month"])
    df = df[df["market"] == "consolidated"].copy()
    df = df.sort_values("month").reset_index(drop=True)

    if df.isnull().any().any():
        print("WARNING: Null values found. Forward-filling.")
        df = df.ffill()

    date_range = pd.date_range(start=df["month"].min(), end=df["month"].max(), freq="MS")
    assert len(df) == len(date_range), (
        f"Missing months! Expected {len(date_range)} months, got {len(df)}"
    )

    print(f"Data loaded: {len(df)} months from {df['month'].min().date()} to {df['month'].max().date()}")
    return df


def engineer_features(df):
    """Create features from the time series with no future leakage.

    All causal (lag) features use only past data. Rolling statistics
    are computed on expanding windows to avoid look-ahead bias.
    Calendar features are deterministic from the month value.
    """
    feats = df[["month", "revenue_eur", "shipments_processed",
                 "avg_revenue_per_shipment_eur"]].copy()

    # Calendar / seasonal features (deterministic, no leakage)
    feats["month_num"] = feats["month"].dt.month
    feats["quarter"] = feats["month"].dt.quarter

    # Cyclic encoding for month (so Dec-Jan proximity is captured)
    feats["month_sin"] = np.sin(2 * np.pi * feats["month_num"] / 12)
    feats["month_cos"] = np.cos(2 * np.pi * feats["month_num"] / 12)

    # Season flags (based on the documented seasonality pattern)
    feats["is_peak_season"] = feats["month_num"].isin([11, 12]).astype(int)
    feats["is_low_season"] = (feats["month_num"] == 2).astype(int)

    # Year index for trend (0 = first year)
    feats["year_idx"] = (feats["month"].dt.year - feats["month"].dt.year.min()).astype(int)

    # Causal lag features (no future leakage)
    for lag in [1, 2, 3, 12]:
        feats[f"revenue_lag_{lag}"] = feats["revenue_eur"].shift(lag)

    for lag in [1, 12]:
        feats[f"shipments_lag_{lag}"] = feats["shipments_processed"].shift(lag)
        feats[f"avg_rev_per_ship_lag_{lag}"] = feats["avg_revenue_per_shipment_eur"].shift(lag)

    # Rolling statistics (shifted to avoid leakage)
    feats["revenue_ma_3"] = feats["revenue_eur"].shift(1).rolling(3, min_periods=1).mean()
    feats["revenue_ma_6"] = feats["revenue_eur"].shift(1).rolling(6, min_periods=1).mean()
    feats["revenue_ma_12"] = feats["revenue_eur"].shift(1).rolling(12, min_periods=1).mean()

    # YoY growth rate (safe: uses value from 12 months ago)
    feats["revenue_yoy_change"] = (
        (feats["revenue_eur"] - feats["revenue_lag_12"]) / feats["revenue_lag_12"]
    ).replace([np.inf, -np.inf], np.nan)

    # Drop rows with NaN from lag creation
    feats = feats.dropna().reset_index(drop=True)

    return feats


def split_data(feats, train_years=TRAIN_YEARS, test_years=TEST_YEARS):
    """Split into first 8 years train, last 2 years test."""
    train_end = pd.Timestamp(year=2016 + train_years, month=1, day=1)
    test_start = pd.Timestamp(year=2024, month=1, day=1)

    train_mask = feats["month"] < train_end
    test_mask = feats["month"] >= test_start

    X_train = feats[train_mask].drop(columns=["month", "revenue_eur"]).reset_index(drop=True)
    y_train = feats.loc[train_mask, "revenue_eur"].reset_index(drop=True)

    X_test = feats[test_mask].drop(columns=["month", "revenue_eur"]).reset_index(drop=True)
    y_test = feats.loc[test_mask, "revenue_eur"].reset_index(drop=True)

    print(f"\nTrain period: {feats[train_mask]['month'].min().date()} -> "
          f"{feats[train_mask]['month'].max().date()}  ({len(X_train)} months)")
    print(f"Test  period: {feats[test_mask]['month'].min().date()} -> "
          f"{feats[test_mask]['month'].max().date()}  ({len(X_test)} months)")

    # Verify no overlap
    assert train_mask.sum() + test_mask.sum() == len(feats), \
        "Train + test months do not cover all data!"
    train_max = feats[train_mask]["month"].max()
    test_min = feats[test_mask]["month"].min()
    assert train_max < test_min, \
        f"Data leakage detected! Train max {train_max.date()} >= Test min {test_min.date()}"

    return X_train, X_test, y_train, y_test, feats[train_mask], feats[test_mask]


def scale_features(X_train, X_test):
    """Scale features using training statistics only."""
    scaler = StandardScaler()
    X_train_scaled = pd.DataFrame(
        scaler.fit_transform(X_train), columns=X_train.columns
    )
    X_test_scaled = pd.DataFrame(
        scaler.transform(X_test), columns=X_test.columns
    )
    return X_train_scaled, X_test_scaled, scaler


def compute_mse(y_true, y_pred):
    """MSE and its relative version."""
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)
    avg_revenue = y_true.mean()
    return {
        "mse_eur2": mse,
        "rmse_eur": rmse,
        "avg_monthly_revenue_eur": avg_revenue,
        "rmse_pct": (rmse / avg_revenue) * 100,
    }


def compute_psi(y_true, y_pred, n_bins=10):
    """Population Stability Index - measures distribution shift."""
    combined = np.concatenate([y_true, y_pred])
    bins = np.percentile(combined, np.linspace(0, 100, n_bins + 1))
    bins[-1] += 1e-6

    expected_counts, _ = np.histogram(y_true, bins=bins)
    actual_counts, _ = np.histogram(y_pred, bins=bins)

    expected_pct = expected_counts / len(y_true)
    actual_pct = actual_counts / len(y_pred)

    expected_pct = np.clip(expected_pct, 1e-6, None)
    actual_pct = np.clip(actual_pct, 1e-6, None)

    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return psi


def compute_gini(y_true, y_pred):
    """Gini coefficient for regression - rank ordering ability."""
    from sklearn.metrics import roc_auc_score

    median = np.median(y_true)
    y_binary = (y_true >= median).astype(int)

    try:
        auc = roc_auc_score(y_binary, y_pred)
        gini = 2 * auc - 1
    except ValueError:
        gini = 0.0
    return gini


def compute_k2_score(y_true, y_pred):
    """Kuiper's K2 statistic - sensitive to distribution shape and tails."""
    combined = np.sort(np.concatenate([y_true, y_pred]))
    n_true = len(y_true)
    n_pred = len(y_pred)

    ecdf_true = np.searchsorted(np.sort(y_true), combined, side="right") / n_true
    ecdf_pred = np.searchsorted(np.sort(y_pred), combined, side="right") / n_pred

    d_plus = np.max(ecdf_true - ecdf_pred)
    d_minus = np.max(ecdf_pred - ecdf_true)

    return float(d_plus + d_minus)


def report_metrics(y_train, y_test, y_pred):
    """Compute and display all metrics on the test set."""
    mse_metrics = compute_mse(y_test, y_pred)
    psi = compute_psi(y_test, y_pred)
    gini = compute_gini(y_test, y_pred)
    k2 = compute_k2_score(y_test, y_pred)

    print("\n" + "=" * 60)
    print("  SALES FORECAST MODEL - EVALUATION ON TEST SET")
    print("=" * 60)
    print(f"  MSE:              {mse_metrics['mse_eur2']:>12,.0f} EUR^2")
    print(f"  RMSE:             {mse_metrics['rmse_eur']:>12,.0f} EUR")
    print(f"  Avg monthly rev:  {mse_metrics['avg_monthly_revenue_eur']:>12,.0f} EUR")
    print(f"  RMSE (%% of avg):  {mse_metrics['rmse_pct']:>12.2f}%%")
    print(f"  PSI:              {psi:>12.4f}")
    print(f"  Gini:             {gini:>12.4f}")
    print(f"  K2 Score:         {k2:>12.4f}")
    print("=" * 60)

    if psi < 0.10:
        psi_msg = "No significant distribution shift (PSI < 0.10)"
    elif psi < 0.25:
        psi_msg = "Moderate distribution shift (0.10 <= PSI < 0.25)"
    else:
        psi_msg = (
            "Significant distribution shift (PSI >= 0.25) - "
            "the revenue mix may have changed between training and test periods"
        )
    print(f"  PSI interpretation: {psi_msg}")

    return {"mse_eur2": mse_metrics["mse_eur2"], "rmse_eur": mse_metrics["rmse_eur"],
            "rmse_pct": mse_metrics["rmse_pct"], "psi": psi, "gini": gini, "k2_score": k2}


def plot_forecast(train_df, test_df, y_test, y_pred, std_pred=None, output_path=None):
    """Plot training data, test predictions, and variability range."""
    matplotlib.use("Agg")
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.plot(
        train_df["month"], train_df["revenue_eur"],
        color="#2196F3", label="Training data (actual)",
        linewidth=1.5, alpha=0.8,
    )

    ax.plot(
        test_df["month"], y_test,
        color="#4CAF50", label="Test data (actual)",
        linewidth=2.0, marker="o", markersize=5,
    )

    ax.plot(
        test_df["month"], y_pred,
        color="#FF5722", label="Forecast (predicted)",
        linewidth=2.0, marker="s", markersize=5, linestyle="--",
    )

    if std_pred is not None:
        lower = y_pred - 1.96 * std_pred
        upper = y_pred + 1.96 * std_pred
        ax.fill_between(
            test_df["month"], lower, upper,
            color="#FF5722", alpha=0.15,
            label="95% prediction interval",
        )

    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Revenue (EUR)", fontsize=12)
    ax.set_title("TrackFlow - Monthly Revenue Forecast (8-year train / 2-year test)", fontsize=14)
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"EUR{x:,.0f}"))

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150)
        print(f"\nVisualization saved to: {output_path}")
    plt.close()


def main():
    """Run the full sales forecast pipeline."""
    print("=" * 60)
    print("  TrackFlow - Sales Forecast Model")
    print("  Algorithm: Random Forest Regressor")
    print("=" * 60)

    df = load_data(DATA_PATH)
    feats = engineer_features(df)
    print(f"Features engineered: {feats.shape[1] - 2} features for {len(feats)} months")

    X_train, X_test, y_train, y_test, train_df, test_df = split_data(feats)
    X_train_scaled, X_test_scaled, scaler = scale_features(X_train, X_test)
    print(f"Features after scaling: {X_train_scaled.shape[1]}")

    # Train Random Forest
    print("\nTraining Random Forest regressor...")
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=8,
        min_samples_leaf=3,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    model.fit(X_train_scaled, y_train)
    print(f"Model trained with {model.n_estimators} trees.")

    # Feature importance summary
    importances = pd.Series(
        model.feature_importances_, index=X_train.columns
    ).sort_values(ascending=False)
    print("\nTop 10 most important features:")
    for name, imp in importances.head(10).items():
        print(f"  {name:35s}  {imp:.4f}")

    y_pred = model.predict(X_test_scaled)

    # Estimate prediction interval from tree ensemble std
    tree_preds = np.array([tree.predict(X_test_scaled) for tree in model.estimators_])
    y_pred_std = tree_preds.std(axis=0)

    metrics = report_metrics(y_train.values, y_test.values, y_pred)

    viz_path = OUTPUT_DIR / "sales_forecast.png"
    plot_forecast(train_df, test_df, y_test.values, y_pred, std_pred=y_pred_std, output_path=viz_path)

    return metrics


if __name__ == "__main__":
    metrics = main()