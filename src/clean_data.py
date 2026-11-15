"""Validate and clean synthetic VoltMart sales without future-data imputation."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_COLUMNS = [
    "transaction_id",
    "line_id",
    "date",
    "product_id",
    "product_name",
    "category",
    "quantity",
    "unit_price",
]


def read_csv(path):
    """Read text values consistently and return useful input errors."""
    try:
        frame = pd.read_csv(path, dtype="string")
    except FileNotFoundError:
        raise ValueError(f"File not found: {path}") from None
    except pd.errors.EmptyDataError:
        raise ValueError(f"File is empty: {path}") from None
    except (pd.errors.ParserError, UnicodeError):
        raise ValueError(f"Cannot read a valid UTF-8 CSV: {path}") from None

    if frame.empty:
        raise ValueError(f"File contains no data rows: {path}")

    return frame


def clean_sales(sales, products):
    """Return clean rows, rejected rows, and a quality summary."""
    missing = set(REQUIRED_COLUMNS) - set(sales.columns)
    if missing:
        raise ValueError(
            f"Sales data is missing columns: {', '.join(sorted(missing))}"
        )

    catalog_columns = {"product_id", "product_name", "category"}
    missing = catalog_columns - set(products.columns)
    if missing:
        raise ValueError(
            f"Catalogue is missing columns: {', '.join(sorted(missing))}"
        )

    if sales.empty or products.empty:
        raise ValueError("Sales data and product catalogue must contain rows.")

    sales = sales[REQUIRED_COLUMNS].copy().astype("string")
    products = products[list(sorted(catalog_columns))].copy().astype("string")

    input_rows = len(sales)

    # Keep original records in the rejected output for investigation.
    original = sales.copy()

    # Normalize surrounding whitespace and blank values.
    for column in products.columns:
        products[column] = products[column].str.strip().replace("", pd.NA)

    if products.isna().any().any():
        raise ValueError("Catalogue contains missing product details.")

    if products["product_id"].duplicated().any():
        raise ValueError("Catalogue contains duplicate product IDs.")

    whitespace_cells = 0
    for column in sales.columns:
        stripped = sales[column].str.strip()
        whitespace_cells += int(
            sales[column].ne(stripped).fillna(False).sum()
        )
        sales[column] = stripped.replace("", pd.NA)

    duplicate_mask = sales.duplicated(keep="first")
    duplicates_removed = int(duplicate_mask.sum())
    sales = sales.loc[~duplicate_mask].copy()
    original = original.loc[sales.index].copy()

    # Store every reason when a row has multiple problems.
    reasons = pd.Series("", index=sales.index, dtype="string")

    def flag(mask, message):
        mask = mask.fillna(False)
        reasons.loc[mask] = reasons.loc[mask] + message + "; "

    for column in ["transaction_id", "line_id", "date", "product_id"]:
        flag(sales[column].isna(), f"missing {column}")

    flag(
        sales["line_id"].notna()
        & sales["line_id"].duplicated(keep=False),
        "conflicting line_id",
    )

    catalog = products.set_index("product_id")
    known_product = sales["product_id"].isin(catalog.index)
    flag(
        sales["product_id"].notna() & ~known_product,
        "unknown product_id",
    )

    # Static catalogue metadata is safe to use here. No sales averages
    # or observations from future dates are used.
    names_filled = 0
    categories_filled = 0

    for column in ["product_name", "category"]:
        expected = sales["product_id"].map(catalog[column])
        fill_mask = known_product & sales[column].isna()
        sales.loc[fill_mask, column] = expected.loc[fill_mask]

        if column == "product_name":
            names_filled = int(fill_mask.sum())
        else:
            categories_filled = int(fill_mask.sum())

        flag(
            known_product
            & sales[column].notna()
            & sales[column].ne(expected),
            f"{column} does not match catalogue",
        )

    # Require the documented date format, including leading zeros.
    date_format_ok = sales["date"].str.fullmatch(
        r"\d{4}-\d{2}-\d{2}", na=False
    )
    dates = pd.to_datetime(
        sales["date"].where(date_format_ok),
        format="%Y-%m-%d",
        errors="coerce",
    )
    flag(dates.isna(), "invalid date")

    quantities = pd.to_numeric(sales["quantity"], errors="coerce")
    prices = pd.to_numeric(sales["unit_price"], errors="coerce")

    quantity_valid = (
        quantities.notna()
        & np.isfinite(quantities)
        & quantities.gt(0)
        & quantities.mod(1).eq(0)
        & quantities.le(np.iinfo(np.int64).max)
    )
    price_valid = (
        prices.notna()
        & np.isfinite(prices)
        & prices.gt(0)
    )

    flag(~quantity_valid, "quantity must be a positive whole number")
    flag(~price_valid, "unit_price must be a positive finite number")

    valid = reasons.eq("")

    rejected = original.loc[~valid].copy()
    rejected["rejection_reason"] = reasons.loc[~valid].str.rstrip("; ")

    cleaned = sales.loc[valid].copy()
    cleaned["date"] = dates.loc[valid].dt.strftime("%Y-%m-%d")
    cleaned["quantity"] = quantities.loc[valid].astype("int64")
    cleaned["unit_price"] = prices.loc[valid].astype("float64")
    cleaned = cleaned.sort_values(
        ["date", "product_id", "line_id"]
    ).reset_index(drop=True)

    reason_counts = (
        rejected["rejection_reason"]
        .str.split("; ")
        .explode()
        .value_counts()
        .to_dict()
    )

    report = {
        "input_rows": input_rows,
        "duplicates_removed": duplicates_removed,
        "rejected_rows": len(rejected),
        "clean_rows": len(cleaned),
        "whitespace_cells_trimmed": whitespace_cells,
        "product_names_filled": names_filled,
        "categories_filled": categories_filled,
        "rejection_reason_counts": {
            reason: int(count) for reason, count in reason_counts.items()
        },
        "row_accounting_passed": (
            input_rows
            == duplicates_removed + len(rejected) + len(cleaned)
        ),
        "missing_value_policy": (
            "Reject missing quantities and prices; restore missing product "
            "metadata from the supplied static catalogue."
        ),
    }

    return cleaned, rejected.reset_index(drop=True), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path,
        default=ROOT / "data/raw/sales_raw.csv",
    )
    parser.add_argument(
        "--products", type=Path,
        default=ROOT / "data/raw/products.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "data/processed",
    )
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "reports/cleaning_report.json",
    )
    args = parser.parse_args()

    try:
        sales = read_csv(args.input)
        products = read_csv(args.products)
        cleaned, rejected, report = clean_sales(sales, products)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)

        cleaned.to_csv(args.output_dir / "sales_clean.csv", index=False)
        rejected.to_csv(
            args.output_dir / "sales_rejected.csv", index=False
        )
        args.report.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    except (ValueError, OSError) as error:
        parser.exit(status=1, message=f"Error: {error}\n")

    print(json.dumps(report, indent=2))
    print(f"\nOutputs saved to: {args.output_dir}")
    print(f"Quality report saved to: {args.report}")

    if cleaned.empty:
        parser.exit(
            status=1,
            message="No usable sales remain. Review the rejected records.\n",
        )


if __name__ == "__main__":
    main()