"""Build calendar-complete daily sales with explicit uncertainty."""

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def build_daily_sales(clean, rejected, products, raw):
    product_ids = products["product_id"].tolist()

    raw = raw.copy()
    raw["parsed_date"] = pd.to_datetime(
        raw["date"], format="%Y-%m-%d", errors="coerce"
    )

    valid_dates = raw["parsed_date"].dropna()
    if valid_dates.empty:
        raise ValueError("No valid dates exist in the raw data.")

    days = pd.date_range(valid_dates.min(), valid_dates.max())
    index = pd.MultiIndex.from_product(
        [days, product_ids], names=["date", "product_id"]
    )

    clean = clean.copy()
    clean["date"] = pd.to_datetime(
        clean["date"], format="%Y-%m-%d", errors="raise"
    )

    totals = clean.groupby(["date", "product_id"])["quantity"].sum()
    daily = totals.reindex(index).rename("daily_units").reset_index()
    daily["status"] = "observed"
    daily.loc[daily["daily_units"].isna(), "status"] = "assumed_zero"
    daily["daily_units"] = daily["daily_units"].fillna(0)

    # A transaction's lines share a sale date in this sample.
    transaction_dates = (
        raw.dropna(subset=["parsed_date"])
        .groupby("transaction_id")["parsed_date"]
        .agg(lambda values: sorted(set(values)))
    )

    for _, row in rejected.iterrows():
        date = pd.to_datetime(
            row["date"], format="%Y-%m-%d", errors="coerce"
        )
        product = row["product_id"]

        if pd.isna(date):
            candidates = transaction_dates.get(row["transaction_id"], [])
            if len(candidates) == 1:
                date = candidates[0]

        known_product = product in product_ids

        if pd.notna(date) and known_product:
            affected = (
                daily["date"].eq(date)
                & daily["product_id"].eq(product)
            )
        elif pd.notna(date):
            # The sale could belong to any catalogue product that day.
            affected = daily["date"].eq(date)
        elif known_product:
            # Its date cannot be located within the sample period.
            affected = daily["product_id"].eq(product)
        else:
            affected = pd.Series(True, index=daily.index)

        daily.loc[affected, "daily_units"] = float("nan")
        daily.loc[affected, "status"] = "unknown"

    return daily.sort_values(
        ["product_id", "date"]
    ).reset_index(drop=True)


def main():
    try:
        clean = pd.read_csv(ROOT / "data/processed/sales_clean.csv")
        rejected = pd.read_csv(ROOT / "data/processed/sales_rejected.csv")
        products = pd.read_csv(ROOT / "data/raw/products.csv")
        raw = pd.read_csv(ROOT / "data/raw/sales_raw.csv")

        daily = build_daily_sales(clean, rejected, products, raw)

        output = ROOT / "data/processed/daily_sales.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        daily.to_csv(output, index=False)

        print("Daily table status counts:")
        print(daily["status"].value_counts().to_string())

        example = daily[
            daily["product_id"].eq("PRD-001")
            & daily["date"].between("2026-05-01", "2026-05-14")
        ]
        print("\nWireless Mouse: 14 consecutive days")
        print(example.to_string(index=False))
        print(f"\nSaved: {output}")

    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f"Error: {error}") from None


if __name__ == "__main__":
    main()