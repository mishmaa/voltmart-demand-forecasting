import pandas as pd
import pytest

from src.baseline import evaluate_baseline
from src.build_daily_sales import build_daily_sales


def daily_sample():
    return pd.DataFrame({
        "date": pd.date_range("2026-05-01", periods=14),
        "product_id": ["PRD-001"] * 14,
        "daily_units": list(range(1, 15)),
        "status": ["observed"] * 14,
    })


def test_weekly_predictions_and_mae():
    predictions, _, report = evaluate_baseline(daily_sample())
    scored = predictions[predictions["scored"]]

    assert scored["prediction"].tolist() == list(range(1, 8))
    assert scored["actual"].tolist() == list(range(8, 15))
    assert scored["absolute_error"].tolist() == [7] * 7
    assert report["mae_units"] == pytest.approx(7)
    assert report["scored_product_days"] == 7
    assert report["scoring_coverage_percent"] == 100

    assert (
        scored["date"] - scored["source_date"]
    ).eq(pd.Timedelta(days=7)).all()


def test_unknown_lag_prevents_prediction():
    daily = daily_sample()
    daily.loc[0, ["daily_units", "status"]] = [float("nan"), "unknown"]

    predictions, _, report = evaluate_baseline(daily)
    target = predictions[
        predictions["date"].eq(pd.Timestamp("2026-05-08"))
    ].iloc[0]

    assert pd.isna(target["prediction"])
    assert not target["scored"]
    assert report["scored_product_days"] == 6


def test_unknown_actual_excluded_from_mae():
    daily = daily_sample()
    daily.loc[7, ["daily_units", "status"]] = [float("nan"), "unknown"]

    predictions, _, report = evaluate_baseline(daily)
    target = predictions[
        predictions["date"].eq(pd.Timestamp("2026-05-08"))
    ].iloc[0]

    assert target["prediction"] == 1
    assert not target["scored"]
    assert report["scored_product_days"] == 6


def test_later_values_do_not_change_earlier_predictions():
    daily = daily_sample()
    before, _, _ = evaluate_baseline(daily)

    changed = daily.copy()
    changed.loc[13, "daily_units"] = 999
    after, _, _ = evaluate_baseline(changed)

    pd.testing.assert_frame_equal(
        before[["date", "product_id", "prediction"]],
        after[["date", "product_id", "prediction"]],
    )


def test_appending_future_days_preserves_existing_predictions():
    daily = daily_sample()
    before, _, _ = evaluate_baseline(daily)

    future = pd.DataFrame({
        "date": pd.date_range("2026-05-15", periods=7),
        "product_id": ["PRD-001"] * 7,
        "daily_units": [999] * 7,
        "status": ["observed"] * 7,
    })
    after, _, _ = evaluate_baseline(
        pd.concat([daily, future], ignore_index=True)
    )

    columns = ["date", "product_id", "prediction"]
    existing = after[after["date"].le(daily["date"].max())]

    pd.testing.assert_frame_equal(
        before[columns].reset_index(drop=True),
        existing[columns].reset_index(drop=True),
    )


@pytest.mark.parametrize("case", ["empty", "missing_column", "gap", "duplicate"])
def test_invalid_inputs(case):
    daily = daily_sample()

    if case == "empty":
        daily = daily.iloc[:0]
    elif case == "missing_column":
        daily = daily.drop(columns="status")
    elif case == "gap":
        daily = daily.drop(index=3)
    else:
        daily = pd.concat([daily, daily.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError):
        evaluate_baseline(daily)


def test_daily_table_sums_units_and_marks_rejected_day_unknown():
    products = pd.DataFrame({"product_id": ["PRD-001"]})

    clean = pd.DataFrame({
        "date": ["2026-05-01", "2026-05-01"],
        "product_id": ["PRD-001", "PRD-001"],
        "quantity": [2, 3],
    })

    raw = pd.DataFrame({
        "transaction_id": ["TXN-1", "TXN-2", "TXN-3"],
        "date": ["2026-05-01", "2026-05-01", "2026-05-03"],
        "product_id": ["PRD-001"] * 3,
    })
    rejected = raw.iloc[[2]].copy()

    daily = build_daily_sales(clean, rejected, products, raw)

    assert len(daily) == 3
    assert daily.iloc[0]["daily_units"] == 5
    assert daily.iloc[0]["status"] == "observed"
    assert daily.iloc[1]["daily_units"] == 0
    assert daily.iloc[1]["status"] == "assumed_zero"
    assert pd.isna(daily.iloc[2]["daily_units"])
    assert daily.iloc[2]["status"] == "unknown"


def test_rejected_sale_masks_partial_clean_total():
    products = pd.DataFrame({"product_id": ["PRD-001"]})
    raw = pd.DataFrame({
        "transaction_id": ["TXN-1", "TXN-2"],
        "date": ["2026-05-01", "2026-05-01"],
        "product_id": ["PRD-001", "PRD-001"],
    })
    clean = pd.DataFrame({
        "date": ["2026-05-01"],
        "product_id": ["PRD-001"],
        "quantity": [2],
    })

    daily = build_daily_sales(clean, raw.iloc[[1]], products, raw)

    assert daily.iloc[0]["status"] == "unknown"
    assert pd.isna(daily.iloc[0]["daily_units"])