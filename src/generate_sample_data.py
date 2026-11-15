"""Generate reproducible synthetic sales and controlled data-quality issues."""

from pathlib import Path
import random

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SEED = 42


def main():
    rng = random.Random(SEED)
    catalog_path = RAW_DIR / "products.csv"

    if not catalog_path.exists():
        raise SystemExit(
            "Product catalogue missing. Create data/raw/products.csv first."
        )

    products = pd.read_csv(catalog_path)
    required = {
        "product_id", "product_name", "category", "reference_price_pkr"
    }

    if products.empty or not required.issubset(products.columns):
        raise SystemExit("Product catalogue is empty or missing required columns.")

    records = []
    line_number = 1
    transaction_number = 1

    # A fixed historical period makes the sample repeatable.
    for date in pd.date_range("2026-05-01", "2026-10-31"):
        # More transactions on weekends, with gradual growth over time.
        daily_transactions = rng.randint(8, 14)
        daily_transactions += 4 if date.dayofweek >= 5 else 0
        daily_transactions += (date.month - 5) // 2

        for _ in range(daily_transactions):
            transaction_id = f"TXN-{transaction_number:06d}"
            transaction_number += 1

            # A purchase may include one or two different products.
            selected = rng.sample(
                products.to_dict("records"),
                k=rng.choices([1, 2], weights=[75, 25])[0],
            )

            for product in selected:
                quantity = (
                    rng.randint(1, 3)
                    if product["category"] in {"Accessories", "Audio"}
                    else 1
                )
                discount = rng.choice([1.0, 1.0, 1.0, 0.95, 0.90])

                records.append({
                    "transaction_id": transaction_id,
                    "line_id": f"LINE-{line_number:06d}",
                    "date": date.strftime("%Y-%m-%d"),
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "category": product["category"],
                    "quantity": quantity,
                    "unit_price": round(
                        product["reference_price_pkr"] * discount, 2
                    ),
                })
                line_number += 1

    sales = pd.DataFrame(records)
    # Object dtype allows deliberate malformed values in numeric columns.
    sales = sales.astype({"quantity": "object", "unit_price": "object"})

    # Use separate rows for each issue so their effects can be checked.
    indexes = rng.sample(range(len(sales)), 38)

    for index in indexes[0:5]:
        sales.at[index, "quantity"] = None

    for index in indexes[5:10]:
        sales.at[index, "unit_price"] = None

    for index in indexes[10:14]:
        sales.at[index, "date"] = "invalid-date"

    for index in indexes[14:18]:
        sales.at[index, "product_name"] = None

    for index in indexes[18:22]:
        sales.at[index, "quantity"] = -2

    for index in indexes[22:26]:
        sales.at[index, "quantity"] = "two"

    for index in indexes[26:30]:
        sales.at[index, "unit_price"] = 0

    for index in indexes[30:34]:
        sales.at[index, "product_id"] = "UNKNOWN"

    for index in indexes[34:38]:
        sales.at[index, "category"] = (
            f"  {sales.at[index, 'category']}  "
        )

    # Duplicate five otherwise unchanged records.
    duplicate_indexes = [
        index for index in sales.index if index not in indexes
    ][:5]
    sales = pd.concat(
        [sales, sales.loc[duplicate_indexes]], ignore_index=True
    )

    # Shuffling ensures the pipeline must explicitly sort by date.
    sales = sales.sample(frac=1, random_state=SEED).reset_index(drop=True)

    output_path = RAW_DIR / "sales_raw.csv"
    sales.to_csv(output_path, index=False)

    print(f"Created {output_path}")
    print(f"Rows: {len(sales)}")
    print("Period: 2026-05-01 to 2026-10-31")
    print("Synthetic data only; seed: 42")
    print("Injected issues: 38 affected rows plus 5 duplicate rows.")


if __name__ == "__main__":
    main()