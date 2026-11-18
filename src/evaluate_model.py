"""Evaluate the selected Random Forest on October using matching rows."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

if __package__:
    from .features import FEATURE_COLUMNS, build_features
    from .tune_model import make_model
else:
    from features import FEATURE_COLUMNS, build_features
    from tune_model import make_model


ROOT = Path(__file__).resolve().parents[1]


def evaluate_model(daily, selection):
    """Refit selected settings without using October targets for fitting."""
    settings = selection.get("selected_settings", {})

    if selection.get("training_end") != "2026-08-31":
        raise ValueError("Selection must use May-August training.")
    if selection.get("validation_start") != "2026-09-01":
        raise ValueError("Selection must use September validation.")
    if selection.get("validation_end") != "2026-09-30":
        raise ValueError("Selection must end before October.")
    if selection.get("test_evaluated") is not False:
        raise ValueError("Expected a selection made without test evaluation.")
    if selection.get("feature_columns") != FEATURE_COLUMNS:
        raise ValueError("Selection feature columns do not match current code.")

    depth = settings.get("max_depth")
    leaf_size = settings.get("min_samples_leaf")

    if depth not in [3, 6, None]:
        raise ValueError("Selected max_depth is outside the predefined grid.")
    if leaf_size not in [2, 5, 10]:
        raise ValueError("Selected leaf size is outside the predefined grid.")
    if settings.get("n_estimators") != 200:
        raise ValueError("Expected 200 trees.")
    if settings.get("random_state") != 42:
        raise ValueError("Expected random seed 42.")

    features = build_features(daily)

    train = features[
        features["date"].between("2026-05-01", "2026-09-30")
        & features["features_ready"]
        & features["target_known"]
    ].copy()

    test = features[
        features["date"].between("2026-10-01", "2026-10-31")
    ].copy()

    if train.empty:
        raise ValueError("No usable May-September refit rows.")
    if test.empty:
        raise ValueError("No October rows to evaluate.")

    ready = test["features_ready"]
    if not ready.any():
        raise ValueError("No October rows have usable features.")

    unseen = (
        set(test.loc[ready, "product_id"])
        - set(train["product_id"])
    )
    if unseen:
        raise ValueError(
            "Test products without training history: "
            + ", ".join(sorted(unseen))
        )

    model = make_model(depth, leaf_size)
    model.fit(
        train[FEATURE_COLUMNS],
        train["daily_units"],
    )

    predictions = test[
        ["date", "product_id", "daily_units", "status", "lag_7"]
    ].copy().rename(columns={
        "daily_units": "actual",
        "lag_7": "baseline_prediction",
    })

    predictions["model_prediction"] = np.nan
    predicted = model.predict(
        test.loc[ready, FEATURE_COLUMNS]
    )

    if not np.isfinite(predicted).all():
        raise ValueError("Model produced non-finite predictions.")

    predictions.loc[ready, "model_prediction"] = predicted

    # Both methods are scored on exactly the same product-days.
    predictions["scored"] = (
        predictions["actual"].notna()
        & predictions["baseline_prediction"].notna()
        & predictions["model_prediction"].notna()
    )

    scored = predictions["scored"]

    if not scored.any():
        raise ValueError("No matching October rows can be scored.")

    predictions["model_absolute_error"] = (
        predictions["actual"] - predictions["model_prediction"]
    ).abs().where(scored)

    predictions["baseline_absolute_error"] = (
        predictions["actual"] - predictions["baseline_prediction"]
    ).abs().where(scored)

    model_mae = float(
        predictions.loc[scored, "model_absolute_error"].mean()
    )
    baseline_mae = float(
        predictions.loc[scored, "baseline_absolute_error"].mean()
    )

    per_product = predictions.groupby("product_id").agg(
        total_days=("date", "size"),
        model_prediction_days=("model_prediction", "count"),
        scored_days=("scored", "sum"),
        model_mae=("model_absolute_error", "mean"),
        baseline_mae_same_rows=("baseline_absolute_error", "mean"),
    ).reset_index()

    per_product["coverage_percent"] = (
        100 * per_product["scored_days"] / per_product["total_days"]
    ).round(2)

    excluded = per_product.loc[
        per_product["scored_days"].eq(0), "product_id"
    ].tolist()

    summary = {
        "model": "RandomForestRegressor",
        "sklearn_version": sklearn.__version__,
        "selected_settings": settings,
        "refit_start": "2026-05-01",
        "refit_end": "2026-09-30",
        "test_start": "2026-10-01",
        "test_end": "2026-10-31",
        "refit_rows": len(train),
        "test_total_product_days": len(test),
        "model_predictions_available": int(
            predictions["model_prediction"].notna().sum()
        ),
        "matched_scored_product_days": int(scored.sum()),
        "matched_scoring_coverage_percent": round(
            100 * int(scored.sum()) / len(test), 2
        ),
        "total_products": int(test["product_id"].nunique()),
        "scored_products": int(
            predictions.loc[scored, "product_id"].nunique()
        ),
        "excluded_product_ids": excluded,
        "model_mae_units": model_mae,
        "baseline_mae_same_rows": baseline_mae,
        "mae_reduction_units": baseline_mae - model_mae,
        "mae_reduction_percent": (
            100 * (baseline_mae - model_mae) / baseline_mae
            if baseline_mae > 0 else None
        ),
        "evaluation_protocol": (
            "Fixed model refitted on May-September. October predictions "
            "use actual history strictly before each prediction day. "
            "No October refitting or hyperparameter selection."
        ),
        "limitations": [
            "Fixed retrospectively audited daily data.",
            "Earlier baseline work included October observations.",
            "Unknown history and strict feature requirements reduce coverage.",
            "Synthetic data does not establish real-world accuracy.",
        ],
    }

    return predictions.reset_index(drop=True), per_product, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/processed/daily_sales.csv",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=ROOT / "reports/tuning/selection.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports/improved_model",
    )
    args = parser.parse_args()

    try:
        daily = pd.read_csv(args.input)
        selection = json.loads(
            args.selection.read_text(encoding="utf-8")
        )

        if not isinstance(selection, dict):
            raise ValueError("Selection JSON must contain an object.")
        if not isinstance(selection.get("selected_settings"), dict):
            raise ValueError("Selection JSON has no valid selected_settings.")

        predictions, per_product, summary = evaluate_model(
            daily, selection
        )

        args.output_dir.mkdir(parents=True, exist_ok=True)

        predictions.to_csv(
            args.output_dir / "predictions.csv", index=False
        )
        per_product.to_csv(
            args.output_dir / "per_product_metrics.csv", index=False
        )

        (args.output_dir / "metrics.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False),
            encoding="utf-8",
        )

    except (ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")

    print(json.dumps(summary, indent=2, allow_nan=False))
    print("\nPer-product results:")
    print(per_product.to_string(index=False))


if __name__ == "__main__":
    main()