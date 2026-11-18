"""Tune a Random Forest on September without evaluating October."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

if __package__:
    from .features import (
        FEATURE_COLUMNS,
        NUMERIC_FEATURES,
        build_features,
    )
else:
    from features import (
        FEATURE_COLUMNS,
        NUMERIC_FEATURES,
        build_features,
    )


ROOT = Path(__file__).resolve().parents[1]

DEPTHS = [3, 6, None]
LEAF_SIZES = [2, 5, 10]


def make_model(max_depth, min_samples_leaf):
    """Build a pipeline whose preprocessing is fitted on training rows."""
    preprocessing = ColumnTransformer([
        (
            "product",
            OneHotEncoder(
                handle_unknown="error",
                sparse_output=False,
            ),
            ["product_id"],
        ),
        (
            "numeric",
            "passthrough",
            NUMERIC_FEATURES,
        ),
    ])

    forest = RandomForestRegressor(
        n_estimators=200,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=42,
        n_jobs=1,
    )

    return Pipeline([
        ("preprocessing", preprocessing),
        ("model", forest),
    ])


def tune_model(daily):
    """Select settings using September, excluding October from tuning."""
    required = {"date", "product_id", "daily_units", "status"}
    missing = required - set(daily.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {', '.join(sorted(missing))}"
        )

    if daily.empty:
        raise ValueError("Daily sales contains no rows.")

    daily = daily.copy()
    dates = pd.to_datetime(
        daily["date"],
        format="%Y-%m-%d",
        errors="coerce",
    )

    if dates.isna().any():
        raise ValueError("Daily sales contains invalid dates.")

    daily["date"] = dates

    # Remove October before feature construction or model selection.
    history = daily[
        daily["date"].between(
            "2026-05-01",
            "2026-09-30",
        )
    ].copy()

    features = build_features(history)
    usable = (
        features["features_ready"]
        & features["target_known"]
    )

    train = features[
        usable
        & features["date"].between(
            "2026-05-01",
            "2026-08-31",
        )
    ].copy()

    validation = features[
        usable
        & features["date"].between(
            "2026-09-01",
            "2026-09-30",
        )
    ].copy()

    if train.empty:
        raise ValueError("No usable May-August training rows.")

    if validation.empty:
        raise ValueError("No usable September validation rows.")

    unseen_products = (
        set(validation["product_id"])
        - set(train["product_id"])
    )

    if unseen_products:
        raise ValueError(
            "Validation products without training history: "
            + ", ".join(sorted(unseen_products))
        )

    X_train = train[FEATURE_COLUMNS]
    y_train = train["daily_units"]

    X_validation = validation[FEATURE_COLUMNS]
    y_validation = validation["daily_units"]

    rows = []
    best_key = None
    best_predictions = None
    best_settings = None

    for depth in DEPTHS:
        for leaf_size in LEAF_SIZES:
            model = make_model(depth, leaf_size)
            model.fit(X_train, y_train)

            predictions = model.predict(X_validation)

            if not np.isfinite(predictions).all():
                raise ValueError(
                    "Model produced non-finite predictions."
                )

            mae = float(
                mean_absolute_error(
                    y_validation,
                    predictions,
                )
            )

            rows.append({
                "max_depth": (
                    "unlimited" if depth is None else str(depth)
                ),
                "min_samples_leaf": leaf_size,
                "n_estimators": 200,
                "validation_rows": len(validation),
                "validation_mae": mae,
            })

            # Exact score ties prefer shallower trees, then larger leaves.
            candidate_key = (
                mae,
                float("inf") if depth is None else depth,
                -leaf_size,
            )

            if best_key is None or candidate_key < best_key:
                best_key = candidate_key
                best_predictions = predictions.copy()

                best_settings = {
                    "max_depth": depth,
                    "min_samples_leaf": leaf_size,
                    "n_estimators": 200,
                    "random_state": 42,
                }

    if best_settings is None:
        raise ValueError("The tuning search contains no candidates.")

    results = (
        pd.DataFrame(rows)
        .sort_values("validation_mae", kind="stable")
        .reset_index(drop=True)
    )

    # Every candidate and the baseline use identical validation rows.
    baseline_mae = float(
        mean_absolute_error(
            y_validation,
            validation["lag_7"],
        )
    )

    validation_predictions = validation[
        [
            "date",
            "product_id",
            "daily_units",
            "lag_7",
        ]
    ].copy()

    validation_predictions = validation_predictions.rename(
        columns={
            "daily_units": "actual",
            "lag_7": "baseline_prediction",
        }
    )

    validation_predictions["model_prediction"] = best_predictions

    validation_total_rows = int(
        features["date"].between(
            "2026-09-01",
            "2026-09-30",
        ).sum()
    )

    summary = {
        "model": "RandomForestRegressor",
        "sklearn_version": sklearn.__version__,
        "training_start": "2026-05-01",
        "training_end": "2026-08-31",
        "validation_start": "2026-09-01",
        "validation_end": "2026-09-30",
        "reserved_test_start": "2026-10-01",
        "reserved_test_end": "2026-10-31",
        "training_rows": len(train),
        "validation_total_rows": validation_total_rows,
        "validation_scored_rows": len(validation),
        "validation_coverage_percent": round(
            100 * len(validation) / validation_total_rows,
            2,
        ),
        "candidate_count": len(rows),
        "selected_settings": best_settings,
        "selected_validation_mae": float(best_key[0]),
        "baseline_validation_mae_same_rows": baseline_mae,
        "validation_mae_reduction": (
            baseline_mae - float(best_key[0])
        ),
        "feature_columns": list(FEATURE_COLUMNS),
        "evaluation_protocol": (
            "Fixed May-August fitted model; one-day September "
            "predictions use historical actuals available before "
            "each prediction day. No September refitting."
        ),
        "test_evaluated": False,
        "data_limitation": (
            "Features use the fixed retrospectively audited daily table."
        ),
    }

    return results, summary, validation_predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/processed/daily_sales.csv",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports/tuning",
    )

    args = parser.parse_args()

    try:
        daily = pd.read_csv(args.input)

        results, summary, predictions = tune_model(daily)

        args.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        results.to_csv(
            args.output_dir / "search_results.csv",
            index=False,
        )

        predictions.to_csv(
            args.output_dir / "validation_predictions.csv",
            index=False,
        )

        (args.output_dir / "selection.json").write_text(
            json.dumps(
                summary,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

    except (ValueError, OSError) as error:
        parser.exit(
            1,
            f"Error: {error}\n",
        )

    print(results.to_string(index=False))
    print("\nSelection:")
    print(
        json.dumps(
            summary,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()