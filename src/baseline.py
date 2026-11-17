"""Evaluate a weekly seasonal naive baseline on audited daily sales."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def evaluate_baseline(daily):
    required = {"date", "product_id", "daily_units", "status"}
    missing = required - set(daily.columns)

    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    if daily.empty:
        raise ValueError("Daily sales file contains no rows.")

    daily = daily.copy()
    daily["date"] = pd.to_datetime(
        daily["date"], format="%Y-%m-%d", errors="coerce"
    )

    if daily["date"].isna().any():
        raise ValueError("Daily sales contains invalid dates.")
    if daily["product_id"].isna().any():
        raise ValueError("Daily sales contains missing product IDs.")
    if daily.duplicated(["date", "product_id"]).any():
        raise ValueError("Duplicate product-date rows found.")

    allowed = {"observed", "assumed_zero", "unknown"}
    if not daily["status"].isin(allowed).all():
        raise ValueError("Unrecognized daily sales status.")

    units = pd.to_numeric(daily["daily_units"], errors="coerce")
    known = daily["status"].ne("unknown")

    valid_units = (
        units.notna()
        & np.isfinite(units)
        & units.ge(0)
        & units.mod(1).eq(0)
    )
    if (known & ~valid_units).any():
        raise ValueError("Known totals must be finite nonnegative integers.")
    if (~known & units.notna()).any():
        raise ValueError("Unknown totals must have empty daily_units.")

    daily["daily_units"] = units

    # Require a complete calendar; zero and unknown are explicit rows.
    for product, group in daily.groupby("product_id"):
        expected = pd.date_range(
            group["date"].min(), group["date"].max()
        )
        if len(group) != len(expected):
            raise ValueError(f"Calendar gaps found for {product}.")
        if len(expected) < 8:
            raise ValueError(f"At least 8 daily rows needed for {product}.")

    daily = daily.sort_values(["product_id", "date"])

    # Match exact calendar dates, not simply seven transaction rows back.
    history = daily[["date", "product_id", "daily_units"]].copy()
    history["source_date"] = history["date"]
    history["date"] += pd.Timedelta(days=7)
    history = history.rename(columns={"daily_units": "prediction"})

    predictions = daily.merge(
        history,
        on=["date", "product_id"],
        how="left",
        validate="one_to_one",
    ).rename(columns={"daily_units": "actual"})

    starts = daily.groupby("product_id")["date"].min()
    predictions["eligible"] = predictions["date"].ge(
        predictions["product_id"].map(starts) + pd.Timedelta(days=7)
    )

    predictions["scored"] = (
        predictions["eligible"]
        & predictions["actual"].notna()
        & predictions["prediction"].notna()
    )
    predictions["absolute_error"] = (
        predictions["actual"] - predictions["prediction"]
    ).abs().where(predictions["scored"])

    eligible = predictions[predictions["eligible"]]
    scored = eligible[eligible["scored"]]

    if scored.empty:
        raise ValueError("No dates have both a known actual and weekly lag.")

    report = {
        "method": "weekly_seasonal_naive",
        "horizon_days": 1,
        "season_length_days": 7,
        "evaluation": "expanding-history one-day walk-forward",
        "eligible_product_days": len(eligible),
        "predictions_available": int(eligible["prediction"].notna().sum()),
        "scored_product_days": len(scored),
        "scoring_coverage_percent": round(
            100 * len(scored) / len(eligible), 2
        ),
        "mae_units": float(scored["absolute_error"].mean()),
        "data_scope": (
            "Retrospective evaluation on a fixed audited dataset; "
            "record arrival timestamps are unavailable."
        ),
    }

    per_product = eligible.groupby("product_id").agg(
        eligible_days=("eligible", "size"),
        predicted_days=("prediction", "count"),
        scored_days=("scored", "sum"),
        mae_units=("absolute_error", "mean"),
    ).reset_index()
    per_product["scoring_coverage_percent"] = (
        100 * per_product["scored_days"] / per_product["eligible_days"]
    ).round(2)

    return predictions, per_product, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/processed/daily_sales.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "reports/baseline"
    )
    args = parser.parse_args()

    try:
        daily = pd.read_csv(args.input)
        predictions, per_product, report = evaluate_baseline(daily)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        predictions.to_csv(
            args.output_dir / "predictions.csv", index=False
        )
        per_product.to_csv(
            args.output_dir / "per_product_metrics.csv", index=False
        )
        (args.output_dir / "metrics.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    except (ValueError, OSError, pd.errors.ParserError) as error:
        parser.exit(1, f"Error: {error}\n")

    print(json.dumps(report, indent=2))
    print("\nPer-product results:")
    print(per_product.to_string(index=False))


if __name__ == "__main__":
    main()