import pandas as pd
import pytest

from src.features import FEATURE_COLUMNS, build_features


def sample():
    return pd.DataFrame({
        "date": pd.date_range("2026-05-01", periods=35),
        "product_id": ["PRD-001"] * 35,
        "daily_units": list(range(1, 36)),
        "status": ["observed"] * 35,
    })


def test_feature_values():
    features = build_features(sample())
    row = features.iloc[14]

    assert row["lag_1"] == 14
    assert row["lag_7"] == 8
    assert row["lag_14"] == 1
    assert row["mean_previous_7"] == pytest.approx(11)
    assert row["features_ready"]


def test_today_and_future_cannot_change_todays_features():
    daily = sample()
    before = build_features(daily)

    changed = daily.copy()
    changed.loc[20:, "daily_units"] = 999
    after = build_features(changed)

    pd.testing.assert_frame_equal(
        before.loc[:20, FEATURE_COLUMNS],
        after.loc[:20, FEATURE_COLUMNS],
    )


def test_products_do_not_share_sales_history():
    first = sample()
    second = sample()
    second["product_id"] = "PRD-002"
    second["daily_units"] = 100

    features = build_features(
        pd.concat([first, second], ignore_index=True)
    )
    second_features = features[
        features["product_id"].eq("PRD-002")
    ].reset_index(drop=True)

    assert pd.isna(second_features.iloc[0]["lag_1"])
    assert second_features.iloc[14]["lag_7"] == 100
    assert second_features.iloc[14]["mean_previous_7"] == 100


def test_unknown_history_is_not_filled():
    daily = sample()
    daily.loc[10, ["daily_units", "status"]] = [
        float("nan"), "unknown"
    ]

    features = build_features(daily)

    assert pd.isna(features.iloc[11]["lag_1"])
    assert pd.isna(features.iloc[17]["lag_7"])
    assert pd.isna(features.iloc[24]["lag_14"])
    assert pd.isna(features.iloc[14]["mean_previous_7"])
    assert not features.iloc[14]["features_ready"]


def test_unknown_target_can_still_have_ready_features():
    daily = sample()
    daily.loc[20, ["daily_units", "status"]] = [
        float("nan"), "unknown"
    ]

    features = build_features(daily)

    assert features.iloc[20]["features_ready"]
    assert not features.iloc[20]["target_known"]


def test_calendar_gap_rejected():
    with pytest.raises(ValueError, match="Missing calendar rows"):
        build_features(sample().drop(index=5))


def test_nonzero_assumed_zero_rejected():
    daily = sample()
    daily.loc[0, "status"] = "assumed_zero"

    with pytest.raises(ValueError, match="zero units"):
        build_features(daily)