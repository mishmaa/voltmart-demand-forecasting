import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.clean_data import clean_sales, read_csv


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def products():
    return pd.DataFrame([{
        "product_id": "PRD-001",
        "product_name": "Wireless Mouse",
        "category": "Accessories",
    }])


def sale(**changes):
    row = {
        "transaction_id": "TXN-001",
        "line_id": "LINE-001",
        "date": "2026-05-01",
        "product_id": "PRD-001",
        "product_name": "Wireless Mouse",
        "category": "Accessories",
        "quantity": "2",
        "unit_price": "2500",
    }
    row.update(changes)
    return row


def test_valid_sale(products):
    cleaned, rejected, report = clean_sales(
        pd.DataFrame([sale()]), products
    )

    assert len(cleaned) == 1
    assert rejected.empty
    assert cleaned.iloc[0]["quantity"] == 2
    assert report["row_accounting_passed"]


def test_duplicates_and_metadata_repair(products):
    row = sale(product_name=None, category=" Accessories ")
    cleaned, rejected, report = clean_sales(
        pd.DataFrame([row, row.copy()]), products
    )

    assert len(cleaned) == 1
    assert rejected.empty
    assert cleaned.iloc[0]["product_name"] == "Wireless Mouse"
    assert cleaned.iloc[0]["category"] == "Accessories"
    assert report["duplicates_removed"] == 1
    assert report["product_names_filled"] == 1


@pytest.mark.parametrize(
    "changes,expected_reason",
    [
        ({"quantity": None}, "quantity"),
        ({"quantity": "two"}, "quantity"),
        ({"quantity": "-2"}, "quantity"),
        ({"quantity": "0"}, "quantity"),
        ({"quantity": "1.5"}, "quantity"),
        ({"quantity": "inf"}, "quantity"),
        ({"unit_price": None}, "unit_price"),
        ({"unit_price": "0"}, "unit_price"),
        ({"unit_price": "-10"}, "unit_price"),
        ({"unit_price": "inf"}, "unit_price"),
        ({"date": "2026-02-30"}, "invalid date"),
        ({"date": "01/05/2026"}, "invalid date"),
        ({"product_id": "UNKNOWN"}, "unknown product_id"),
        ({"transaction_id": ""}, "missing transaction_id"),
        ({"product_name": "Wrong name"}, "does not match catalogue"),
    ],
)
def test_invalid_records_are_rejected(
    products, changes, expected_reason
):
    cleaned, rejected, report = clean_sales(
        pd.DataFrame([sale(**changes)]), products
    )

    assert cleaned.empty
    assert len(rejected) == 1
    assert expected_reason in rejected.iloc[0]["rejection_reason"]
    assert report["row_accounting_passed"]


def test_conflicting_line_ids_reject_both_records(products):
    rows = [
        sale(),
        sale(quantity="3"),
    ]
    cleaned, rejected, _ = clean_sales(pd.DataFrame(rows), products)

    assert cleaned.empty
    assert len(rejected) == 2
    assert rejected["rejection_reason"].str.contains(
        "conflicting line_id"
    ).all()


def test_future_sales_do_not_change_past_cleaning(products):
    past = pd.DataFrame([
        sale(line_id="LINE-001"),
        sale(line_id="LINE-002", quantity=None),
    ])

    future = pd.DataFrame([
        sale(
            line_id="LINE-003",
            date="2026-10-31",
            quantity="999",
            unit_price="999999",
        )
    ])

    clean_before, rejected_before, _ = clean_sales(past, products)
    clean_after, rejected_after, _ = clean_sales(
        pd.concat([past, future], ignore_index=True), products
    )

    past_after = clean_after[
        clean_after["date"] == "2026-05-01"
    ].reset_index(drop=True)

    pd.testing.assert_frame_equal(clean_before, past_after)

    assert rejected_before["line_id"].tolist() == ["LINE-002"]
    assert rejected_after["line_id"].tolist() == ["LINE-002"]


def test_missing_required_column(products):
    sales = pd.DataFrame([sale()]).drop(columns="quantity")

    with pytest.raises(ValueError, match="missing columns"):
        clean_sales(sales, products)


def test_empty_csv_has_clear_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        read_csv(path)


def test_missing_file_has_clear_error(tmp_path):
    with pytest.raises(ValueError, match="File not found"):
        read_csv(tmp_path / "missing.csv")


def test_generated_sample_matches_expected_results():
    sales = read_csv(ROOT / "data/raw/sales_raw.csv")
    catalog = read_csv(ROOT / "data/raw/products.csv")

    cleaned, rejected, report = clean_sales(sales, catalog)

    assert report["duplicates_removed"] == 5
    assert len(rejected) == 30
    assert report["product_names_filled"] == 4
    assert report["whitespace_cells_trimmed"] == 4
    assert len(cleaned) == len(sales) - 35
    assert report["row_accounting_passed"]


def test_command_line_missing_input(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "src/clean_data.py"),
            "--input",
            str(tmp_path / "missing.csv"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 1
    assert "File not found" in result.stderr
    assert "Traceback" not in result.stderr