"""Leakage-safe TrackFlow sales model training and evaluation.

Run with ``uv run python scripts/train_sales_forecast.py``. Features are
one-step-ahead: only calendar values and observations strictly before a
month are used to predict that month's consolidated revenue.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
warnings.filterwarnings(
    "ignore",
    message="X has feature names, but DecisionTreeRegressor was fitted without feature names",
)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

RANDOM_SEED = 42
TRAIN_YEARS = 8
TEST_YEARS = 2
CV_SPLITS = 5
CV_TEST_SIZE = 12
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "raw" / "trackflow_sales.csv"
EVAL_DIR = REPO_ROOT / "data" / "eval"


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load and validate the consolidated monthly sales series."""
    df = pd.read_csv(path, parse_dates=["month"])
    required = {"month", "revenue_eur", "shipments_processed", "avg_revenue_per_shipment_eur", "market"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Sales CSV is missing required columns: {sorted(missing)}")
    df = df.loc[df["market"].eq("consolidated")].copy()
    df = df.sort_values("month").reset_index(drop=True)
    if df.empty or df["month"].duplicated().any():
        raise ValueError("Expected one consolidated row per month")
    expected = pd.date_range("2016-01-01", "2025-12-01", freq="MS")
    if not df["month"].reset_index(drop=True).equals(pd.Series(expected, name="month")):
        raise ValueError("Expected complete monthly data from 2016-01 through 2025-12")
    if df["revenue_eur"].isna().any() or (df["revenue_eur"] <= 0).any():
        raise ValueError("revenue_eur must be present and positive")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create strictly causal features; target values are never predictors.

    A feature for month t can use observed values up to t-1. This supports
    rolling one-month-ahead forecasts and preserves legitimate historical
    context at a CV validation boundary without looking forward.
    """
    frame = df[["month", "revenue_eur", "shipments_processed", "avg_revenue_per_shipment_eur"]].copy()
    month_num = frame["month"].dt.month
    frame["month_num"] = month_num
    frame["quarter"] = frame["month"].dt.quarter
    frame["month_sin"] = np.sin(2 * np.pi * month_num / 12)
    frame["month_cos"] = np.cos(2 * np.pi * month_num / 12)
    frame["is_peak_season"] = month_num.isin([11, 12]).astype(int)
    frame["is_low_season"] = month_num.eq(2).astype(int)
    frame["year_idx"] = frame["month"].dt.year - frame["month"].dt.year.min()

    for lag in (1, 2, 3, 12):
        frame[f"revenue_lag_{lag}"] = frame["revenue_eur"].shift(lag)
    for lag in (1, 12):
        frame[f"shipments_lag_{lag}"] = frame["shipments_processed"].shift(lag)
        frame[f"avg_rev_per_shipment_lag_{lag}"] = frame["avg_revenue_per_shipment_eur"].shift(lag)
    for window in (3, 6, 12):
        frame[f"revenue_ma_{window}"] = frame["revenue_eur"].shift(1).rolling(window, min_periods=window).mean()
    frame["revenue_yoy_change"] = (
        frame["revenue_lag_1"] / frame["revenue_lag_12"] - 1
    )
    return frame.dropna().reset_index(drop=True)


def split_data(features: pd.DataFrame, train_years: int = TRAIN_YEARS, test_years: int = TEST_YEARS):
    """Return chronological feature/target train and test data, 8/2 years."""
    # The feature frame begins in 2017 after the 12-month warm-up; recover
    # source-series year 2016 so the train/test boundary remains Jan 2024.
    first_source_year = int(features["month"].dt.year.min()) - 1
    split_date = pd.Timestamp(year=first_source_year + train_years, month=1, day=1)
    test_end = pd.Timestamp(year=first_source_year + train_years + test_years, month=1, day=1)
    train = features.loc[features["month"] < split_date].copy().reset_index(drop=True)
    test = features.loc[(features["month"] >= split_date) & (features["month"] < test_end)].copy().reset_index(drop=True)
    if train.empty or test.empty or train["month"].max() >= test["month"].min():
        raise ValueError("Invalid chronological train/test split")
    return train, test


def feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column not in {"month", "revenue_eur"}]


def make_model() -> RandomForestRegressor:
    """Construct the fixed, reproducible baseline model."""
    return RandomForestRegressor(
        n_estimators=300, max_depth=8, min_samples_leaf=3,
        random_state=RANDOM_SEED, n_jobs=-1,
    )


def make_temporal_cv_splits(frame: pd.DataFrame, n_splits: int = CV_SPLITS, test_size: int = CV_TEST_SIZE):
    """Build expanding-window folds and assert chronological, nonshuffled order."""
    if not frame["month"].is_monotonic_increasing:
        raise ValueError("Time-series CV input must be sorted by month")
    splitter = TimeSeriesSplit(n_splits=n_splits, test_size=test_size)
    splits = list(splitter.split(frame))
    previous_validation_end = -1
    for train_idx, validation_idx in splits:
        if not len(train_idx) or not len(validation_idx):
            raise ValueError("CV folds must have non-empty training and validation windows")
        if train_idx.max() >= validation_idx.min():
            raise ValueError("A CV fold trains on its validation period or later")
        if validation_idx.min() <= previous_validation_end:
            raise ValueError("CV validation folds are not in chronological order")
        if not frame.iloc[train_idx]["month"].is_monotonic_increasing or not frame.iloc[validation_idx]["month"].is_monotonic_increasing:
            raise ValueError("A CV fold is not chronologically ordered")
        previous_validation_end = int(validation_idx.max())
    return splits


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "mae_eur": float(mean_absolute_error(y_true, y_pred)),
        "rmse_eur": float(np.sqrt(mean_squared_error(y_true, y_pred))),
    }


def cross_validate_temporally(train: pd.DataFrame) -> list[dict[str, float | str]]:
    """Evaluate five expanding windows; each scaler/model is fit within-fold."""
    columns = feature_columns(train)
    results = []
    for fold_number, (train_idx, validation_idx) in enumerate(make_temporal_cv_splits(train), start=1):
        fold_train = train.iloc[train_idx]
        fold_validation = train.iloc[validation_idx]
        model = make_model()
        model.fit(fold_train[columns], fold_train["revenue_eur"])
        train_pred = model.predict(fold_train[columns])
        validation_pred = model.predict(fold_validation[columns])
        results.append({
            "fold": fold_number,
            "train_observations": len(fold_train),
            "train_start": fold_train["month"].min().strftime("%Y-%m"),
            "train_end": fold_train["month"].max().strftime("%Y-%m"),
            "validation_start": fold_validation["month"].min().strftime("%Y-%m"),
            "validation_end": fold_validation["month"].max().strftime("%Y-%m"),
            **{f"train_{key}": value for key, value in regression_metrics(fold_train["revenue_eur"], train_pred).items()},
            **{f"validation_{key}": value for key, value in regression_metrics(fold_validation["revenue_eur"], validation_pred).items()},
        })
    return results


def learning_curve_data(train: pd.DataFrame) -> pd.DataFrame:
    """Forward-chaining learning curve, with 2023 as a fixed validation year."""
    validation = train.loc[train["month"].dt.year.eq(int(train["month"].dt.year.max()))]
    pool = train.loc[train["month"] < validation["month"].min()]
    if len(validation) < 6 or len(pool) < 24:
        raise ValueError("Insufficient training history for a temporal learning curve")
    columns = feature_columns(train)
    sizes = sorted(set(np.linspace(24, len(pool), num=5, dtype=int).tolist()))
    rows = []
    for size in sizes:
        subset = pool.iloc[:size]
        model = make_model().fit(subset[columns], subset["revenue_eur"])
        rows.append({
            "train_size": size,
            "train_start": subset["month"].min().strftime("%Y-%m"),
            "train_end": subset["month"].max().strftime("%Y-%m"),
            "train_mae_eur": regression_metrics(subset["revenue_eur"], model.predict(subset[columns]))["mae_eur"],
            "train_rmse_eur": regression_metrics(subset["revenue_eur"], model.predict(subset[columns]))["rmse_eur"],
            "validation_mae_eur": regression_metrics(validation["revenue_eur"], model.predict(validation[columns]))["mae_eur"],
            "validation_rmse_eur": regression_metrics(validation["revenue_eur"], model.predict(validation[columns]))["rmse_eur"],
        })
    return pd.DataFrame(rows)


def plot_learning_curve(curve: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, metric, title in zip(axes, ("mae", "rmse"), ("MAE", "RMSE")):
        ax.plot(curve["train_size"], curve[f"train_{metric}_eur"], marker="o", label="Training")
        ax.plot(curve["train_size"], curve[f"validation_{metric}_eur"], marker="o", label="Validation (2023)")
        ax.set(title=f"TrackFlow temporal learning curve — {title}", xlabel="Training observations", ylabel=f"{title} (EUR)")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_test_forecast(train: pd.DataFrame, test: pd.DataFrame, model, columns: list[str], output_path: Path) -> np.ndarray:
    prediction = model.predict(test[columns])
    tree_predictions = np.stack([tree.predict(test[columns]) for tree in model.estimators_])
    prediction_std = tree_predictions.std(axis=0)
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(train["month"], train["revenue_eur"], label="Training actual", color="#2563EB", alpha=0.7)
    ax.plot(test["month"], test["revenue_eur"], label="Test actual", color="#15803D", marker="o")
    ax.plot(test["month"], prediction, label="Test prediction", color="#EA580C", marker="s", linestyle="--")
    ax.fill_between(test["month"], prediction - 1.96 * prediction_std, prediction + 1.96 * prediction_std,
                    color="#EA580C", alpha=0.16, label="Tree ensemble spread (±1.96 SD; not calibrated interval)")
    ax.set(title="TrackFlow monthly consolidated revenue — 2024–2025 holdout", xlabel="Month", ylabel="Revenue (EUR)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return prediction


def gini_rank_score(y_true, y_pred) -> float:
    """Rank discrimination for high (>= median) vs low revenue months."""
    high_revenue = (np.asarray(y_true) >= np.median(y_true)).astype(int)
    return float(2 * roc_auc_score(high_revenue, y_pred) - 1)


def kuiper_k2(y_true, y_pred) -> float:
    """Kuiper two-sample statistic (D+ + D-) for actual/predicted distributions."""
    actual = np.sort(np.asarray(y_true))
    predicted = np.sort(np.asarray(y_pred))
    values = np.sort(np.concatenate([actual, predicted]))
    actual_cdf = np.searchsorted(actual, values, side="right") / len(actual)
    predicted_cdf = np.searchsorted(predicted, values, side="right") / len(predicted)
    return float(np.max(actual_cdf - predicted_cdf) + np.max(predicted_cdf - actual_cdf))


def summarize(values: list[dict], key: str) -> tuple[float, float]:
    numbers = np.asarray([float(item[key]) for item in values])
    return float(numbers.mean()), float(numbers.std(ddof=1))


def write_report(path: Path, train: pd.DataFrame, test: pd.DataFrame, cv_results: list[dict], curve: pd.DataFrame,
                 train_metrics: dict, test_metrics: dict, test_extras: dict) -> None:
    cv_mae = summarize(cv_results, "validation_mae_eur")
    cv_rmse = summarize(cv_results, "validation_rmse_eur")
    cv_train_mae = summarize(cv_results, "train_mae_eur")
    cv_train_rmse = summarize(cv_results, "train_rmse_eur")
    average_revenue = float(test["revenue_eur"].mean())
    rmse_pct = test_metrics["rmse_eur"] / average_revenue * 100
    curve_gap = float(curve.iloc[-1]["validation_rmse_eur"] - curve.iloc[-1]["train_rmse_eur"])
    gap_ratio = curve_gap / max(float(curve.iloc[-1]["validation_rmse_eur"]), 1.0)
    # Explicit decision based on the final learning-curve gap and held-out CV scores.
    diagnosis = "reasonably well fitted" if gap_ratio < 0.25 else "overfitting"
    recommendation = (
        "Keep the current Random Forest capacity as the baseline; tune/review only after collecting new monthly outcomes. "
        "Do not increase tree depth: the holdout scores and learning-curve gap do not support added complexity."
        if diagnosis == "reasonably well fitted" else
        "Regularize the Random Forest before promotion: reduce max_depth from 8 to 4 and raise min_samples_leaf from 3 to 6, "
        "then rerun the identical forward-chaining CV and compare validation RMSE. This targets the observed train/validation gap."
    )
    fold_lines = "\n".join(
        f"| {row['fold']} | {row['train_start']}–{row['train_end']} ({row['train_observations']} rows) | "
        f"{row['validation_start']}–{row['validation_end']} | €{row['validation_mae_eur']:,.0f} | €{row['validation_rmse_eur']:,.0f} |"
        for row in cv_results
    )
    lines = [
        "# TrackFlow monthly sales regression — technical evaluation", "",
        "## Executive decision", "",
        f"**Diagnosis: {diagnosis}.** The forward-chaining learning curve ends with training RMSE €{curve.iloc[-1]['train_rmse_eur']:,.0f} "
        f"versus 2023 validation RMSE €{curve.iloc[-1]['validation_rmse_eur']:,.0f} (gap €{curve_gap:,.0f}; "
        f"{gap_ratio:.1%} of validation RMSE). Five-fold temporal CV validation RMSE is "
        f"€{cv_rmse[0]:,.0f} ± €{cv_rmse[1]:,.0f}; this indicates {diagnosis} for the available synthetic history.", "",
        f"**Specific action:** {recommendation}", "",
        "## Data and leakage controls", "",
        "Target is `revenue_eur` from the `consolidated` market row. The 2016-01–2023-12 period is training and "
        "2024-01–2025-12 is the untouched 24-month holdout. Twelve early rows are unavailable to modeling because the "
        "12-month lag/rolling history is required; thus the feature matrix contains 84 training and 24 test observations. "
        "No current-month revenue, shipments, or revenue-per-shipment values enter predictors. All lags and rolling means "
        "are shifted so month t uses only observations through t-1. Folds are expanding-window `TimeSeriesSplit` with "
        "five 12-month validation windows; model fitting occurs separately inside every fold. At validation starts, earlier "
        "observed months remain valid causal context for one-month-ahead predictions.", "",
        "## Time-aware cross-validation", "",
        "| Fold | Training period | Validation period | Validation MAE | Validation RMSE |", "|---:|---|---|---:|---:|", fold_lines, "",
        f"Validation MAE: **€{cv_mae[0]:,.0f} ± €{cv_mae[1]:,.0f}** (mean ± sample SD). "
        f"Validation RMSE: **€{cv_rmse[0]:,.0f} ± €{cv_rmse[1]:,.0f}**. "
        f"Fold training MAE: €{cv_train_mae[0]:,.0f} ± €{cv_train_mae[1]:,.0f}; "
        f"training RMSE: €{cv_train_rmse[0]:,.0f} ± €{cv_train_rmse[1]:,.0f}.", "",
        "All training indices precede their validation indices; validation windows move forward without overlap or shuffling. "
        "The tests assert the ordering contract. Feature engineering is causal once on the chronological series; this does "
        "not expose a validation target because each feature uses only earlier values. No scaler or other full-data learned "
        "transform is applied.", "",
        "## Learning curve", "",
        "The curve uses expanding chronological prefixes and a fixed 2023 validation year; the validation year is never "
        "used to fit any plotted model. Training MAE/RMSE are in-sample fit metrics; validation metrics measure the later year.", "",
        "![Training and validation errors by training-set size](sales_learning_curve.png)", "",
        "| Training observations | Training RMSE | 2023 validation RMSE |", "|---:|---:|---:|",
    ]
    lines.extend(f"| {int(row.train_size)} | €{row.train_rmse_eur:,.0f} | €{row.validation_rmse_eur:,.0f} |" for row in curve.itertuples())
    lines += ["", "## Metric choice and 2024–2025 holdout", "",
        "MAE is the primary business metric: each euro of absolute miss has a direct interpretation for revenue planning "
        "and it is not dominated by a few unusually high Black Friday/holiday months. RMSE is reported alongside it because "
        "its stronger penalty for large misses is useful when peak-season forecast errors can affect warehouse and carrier capacity. "
        "The briefing does not establish whether over- or underestimation has a higher asymmetric cost, so neither direction is assigned extra weight.", "",
        f"- Training (2017-01–2023-12, {len(train)} modeled months): MAE **€{train_metrics['mae_eur']:,.0f}**, RMSE **€{train_metrics['rmse_eur']:,.0f}**.",
        f"- Holdout (2024-01–2025-12, {len(test)} months): MAE **€{test_metrics['mae_eur']:,.0f}**, RMSE **€{test_metrics['rmse_eur']:,.0f}**.",
        f"- Holdout MSE: **€{test_extras['mse_eur2']:,.0f} EUR²**; RMSE is **{test_metrics['rmse_eur'] / average_revenue * 100:.2f}%** of mean holdout monthly revenue (€{average_revenue:,.0f}). "
        f"For completeness, the dimensionally unusual MSE/average-revenue ratio is {test_extras['mse_pct_of_average_revenue']:.2f}% (EUR² divided by EUR).",
        f"- Revenue-rank Gini: **{test_extras['gini']:.3f}**; K2 (Kuiper two-sample distribution statistic): **{test_extras['k2_score']:.3f}**.",
        "- Country-mix PSI: **N/A**. The provided CSV has only consolidated rows and no US/Spain shipment split; computing a country volume-mix PSI from it would be unsupported. The provided shipment and average-revenue fields are lagged as inputs, not country-level proportions.", "",
        "![Two-year holdout forecast and ensemble spread](sales_forecast_evaluation.png)", "",
        "The shaded region is ±1.96 times the across-tree prediction standard deviation. It is an ensemble spread visualization, "
        "not a statistically calibrated 95% prediction interval.", "",
        "## Stability and limitations", "",
        f"Five chronological validation RMSEs range from €{min(r['validation_rmse_eur'] for r in cv_results):,.0f} to "
        f"€{max(r['validation_rmse_eur'] for r in cv_results):,.0f}; see mean ± SD above for performance sensitivity to the training window. "
        "These results are a feasibility evaluation on deterministic synthetic sales history, not evidence of future real-world "
        "performance. A holdout spanning increasing annual revenue tests extrapolation beyond the Random Forest's learned target range; "
        "the CV scores should therefore be read together with the fixed 2024–2025 holdout rather than as a deployment guarantee.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> dict:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    features = engineer_features(data)
    train, test = split_data(features)
    cv_results = cross_validate_temporally(train)
    curve = learning_curve_data(train)
    curve.to_csv(EVAL_DIR / "learning_curve_metrics.csv", index=False)
    plot_learning_curve(curve, EVAL_DIR / "sales_learning_curve.png")

    columns = feature_columns(train)
    model = make_model().fit(train[columns], train["revenue_eur"])
    training_metrics = regression_metrics(train["revenue_eur"], model.predict(train[columns]))
    predictions = plot_test_forecast(train, test, model, columns, EVAL_DIR / "sales_forecast_evaluation.png")
    holdout_metrics = regression_metrics(test["revenue_eur"], predictions)
    mean_actual = float(test["revenue_eur"].mean())
    extras = {
        "mse_eur2": float(mean_squared_error(test["revenue_eur"], predictions)),
        "mse_pct_of_average_revenue": float(mean_squared_error(test["revenue_eur"], predictions) / mean_actual * 100),
        "gini": gini_rank_score(test["revenue_eur"], predictions),
        "k2_score": kuiper_k2(test["revenue_eur"], predictions),
    }
    write_report(EVAL_DIR / "evaluation_report.md", train, test, cv_results, curve, training_metrics, holdout_metrics, extras)
    (EVAL_DIR / "evaluation_metrics.json").write_text(json.dumps({"cross_validation": cv_results,
        "training": training_metrics, "holdout": holdout_metrics, **extras}, indent=2), encoding="utf-8")
    print(f"Train/test modeled rows: {len(train)}/{len(test)}")
    print(f"Training MAE/RMSE: €{training_metrics['mae_eur']:,.0f} / €{training_metrics['rmse_eur']:,.0f}")
    print(f"CV validation MAE: €{summarize(cv_results, 'validation_mae_eur')[0]:,.0f} ± €{summarize(cv_results, 'validation_mae_eur')[1]:,.0f}")
    print(f"CV validation RMSE: €{summarize(cv_results, 'validation_rmse_eur')[0]:,.0f} ± €{summarize(cv_results, 'validation_rmse_eur')[1]:,.0f}")
    print(f"Holdout MAE/RMSE: €{holdout_metrics['mae_eur']:,.0f} / €{holdout_metrics['rmse_eur']:,.0f}")
    print(f"Evaluation artifacts: {EVAL_DIR}")
    return {"training": training_metrics, "holdout": holdout_metrics, **extras}


if __name__ == "__main__":
    main()
