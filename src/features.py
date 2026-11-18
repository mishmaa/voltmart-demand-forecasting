"""Build past-only features from calendar-complete daily sales."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

NUMERIC_FEATURES = [
    "weekday",
    "month",
    "days_since_start",
    "lag_1",
    "lag_7",
    "lag_14",
    "mean_previous_7",
]

FEATURE_COLUMNS = ["product_id"] + NUMERIC_FEATURES


def build_features(daily):
    required = {"date", "product_id", "daily_units", "status"}
    missing = required - set(daily.columns)

    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

    if daily.empty:
        raise ValueError("Daily sales contains no rows.")

    frame = daily.copy()
    frame["date"] = pd.to_datetime(
        frame["date"],
        format="%Y-%m-%d",
        errors="coerce",
    )

    if frame["date"].isna().any():
        raise ValueError("Invalid dates in daily sales.")

    if (
        frame["product_id"].isna().any()
        or frame["product_id"].astype(str).str.strip().eq("").any()
    ):
        raise ValueError("Missing product IDs.")

    if frame.duplicated(["product_id", "date"]).any():
        raise ValueError("Duplicate product-date rows.")

    allowed_statuses = ["observed", "assumed_zero", "unknown"]

    if not frame["status"].isin(allowed_statuses).all():
        raise ValueError("Invalid daily sales status.")

    units = pd.to_numeric(frame["daily_units"], errors="coerce")
    known = frame["status"].ne("unknown")

    valid_units = (
        units.notna()
        & np.isfinite(units)
        & units.ge(0)
        & units.mod(1).eq(0)
    )

    if (known & ~valid_units).any():
        raise ValueError(
            "Known totals must be nonnegative finite integers."
        )

    if (~known & frame["daily_units"].notna()).any():
        raise ValueError("Unknown totals must have empty daily_units.")

    if (
        frame["status"].eq("assumed_zero") & units.ne(0)
    ).any():
        raise ValueError("assumed_zero rows must contain zero units.")

    frame["daily_units"] = units
    frame = frame.sort_values(
        ["product_id", "date"]
    ).reset_index(drop=True)

    for product, group in frame.groupby("product_id"):
        expected = pd.date_range(
            group["date"].min(),
            group["date"].max(),
        )

        if len(group) != len(expected):
            raise ValueError(
                f"Missing calendar rows for {product}."
            )

    # Calendar features are known before the forecast day.
    frame["weekday"] = frame["date"].dt.day_of_week
    frame["month"] = frame["date"].dt.month

    # Fixed origin keeps existing features stable when future days are added.
    frame["days_since_start"] = (
        frame["date"] - pd.Timestamp("2026-05-01")
    ).dt.days

    grouped = frame.groupby("product_id")["daily_units"]

    # Calendar rows were validated above, so row shifts represent days.
    for lag in [1, 7, 14]:
        frame[f"lag_{lag}"] = grouped.shift(lag)

    # Shift before rolling: today's actual is excluded from today's mean.
    # Require all seven preceding daily totals to be known.
    frame["mean_previous_7"] = grouped.transform(
        lambda values: values.shift(1).rolling(
            window=7,
            min_periods=7,
        ).mean()
    )

    # Features may be available even when today's target is unknown.
    frame["features_ready"] = (
        frame[FEATURE_COLUMNS].notna().all(axis=1)
    )
    frame["target_known"] = frame["daily_units"].notna()

    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/processed/daily_sales.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/processed/model_features.csv",
    )

    args = parser.parse_args()

    try:
        daily = pd.read_csv(args.input)
        features = build_features(daily)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        features.to_csv(args.output, index=False)

    except (ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")

    print(f"Saved: {args.output}")

    windows = [
        ("Training", "2026-05-01", "2026-08-31"),
        ("Validation", "2026-09-01", "2026-09-30"),
        ("Test", "2026-10-01", "2026-10-31"),
    ]

    for name, start, end in windows:
        subset = features[
            features["date"].between(start, end)
        ]
        usable = (
            subset["features_ready"]
            & subset["target_known"]
        )

        print(
            f"{name}: {len(subset)} total rows; "
            f"{int(usable.sum())} rows with known target "
            "and all features"
        )


if __name__ == "__main__":
    main()