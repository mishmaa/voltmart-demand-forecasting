import numpy as np
import pandas as pd
import pytest

import src.tune_model as tuning


def sample_daily():
    dates = pd.date_range("2026-05-01", "2026-10-31")

    return pd.DataFrame({
        "date": dates,
        "product_id": ["PRD-001"] * len(dates),
        "daily_units": [
            2 + date.day_of_week + (index % 3)
            for index, date in enumerate(dates)
        ],
        "status": ["observed"] * len(dates),
    })


def assert_summaries_equal(before, after):
    """Allow rounding noise in scores, but require identical metadata."""
    assert before.keys() == after.keys()

    for key in before:
        if isinstance(before[key], float):
            assert after[key] == pytest.approx(
                before[key],
                rel=1e-12,
                abs=1e-12,
            ), key
        else:
            assert after[key] == before[key], key


def assert_frames_equal(before, after):
    """Compare numeric results with a tight floating-point tolerance."""
    pd.testing.assert_frame_equal(
        before,
        after,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


@pytest.fixture
def small_search(monkeypatch):
    # Two candidates test selection without running the full grid.
    monkeypatch.setattr(tuning, "DEPTHS", [3])
    monkeypatch.setattr(tuning, "LEAF_SIZES", [2, 5])


def test_selection_uses_lowest_validation_mae(small_search):
    results, summary, predictions = tuning.tune_model(sample_daily())

    assert len(results) == 2
    assert summary["candidate_count"] == 2
    assert summary["test_evaluated"] is False

    assert summary["selected_validation_mae"] == pytest.approx(
        results["validation_mae"].min()
    )

    selected = summary["selected_settings"]

    selected_row = results[
        results["max_depth"].eq(str(selected["max_depth"]))
        & results["min_samples_leaf"].eq(
            selected["min_samples_leaf"]
        )
    ]

    assert len(selected_row) == 1
    assert selected_row.iloc[0]["validation_mae"] == pytest.approx(
        results["validation_mae"].min()
    )

    assert predictions["date"].between(
        "2026-09-01", "2026-09-30"
    ).all()

    expected_model_mae = (
        predictions["actual"] - predictions["model_prediction"]
    ).abs().mean()

    expected_baseline_mae = (
        predictions["actual"] - predictions["baseline_prediction"]
    ).abs().mean()

    assert summary["selected_validation_mae"] == pytest.approx(
        expected_model_mae
    )

    assert summary["baseline_validation_mae_same_rows"] == pytest.approx(
        expected_baseline_mae
    )


def test_october_values_cannot_change_selection(small_search):
    daily = sample_daily()

    results_before, summary_before, predictions_before = (
        tuning.tune_model(daily)
    )

    changed = daily.copy()
    october = changed["date"].ge("2026-10-01")
    changed.loc[october, "daily_units"] = 999999

    results_after, summary_after, predictions_after = (
        tuning.tune_model(changed)
    )

    assert_frames_equal(results_before, results_after)
    assert_frames_equal(predictions_before, predictions_after)
    assert_summaries_equal(summary_before, summary_after)


def test_october_rows_can_be_removed_without_changing_selection(
    small_search,
):
    daily = sample_daily()

    results_before, summary_before, predictions_before = (
        tuning.tune_model(daily)
    )

    without_october = daily[
        daily["date"].lt("2026-10-01")
    ].copy()

    results_after, summary_after, predictions_after = (
        tuning.tune_model(without_october)
    )

    assert_frames_equal(results_before, results_after)
    assert_frames_equal(predictions_before, predictions_after)
    assert_summaries_equal(summary_before, summary_after)


def test_model_fit_uses_only_training_rows(monkeypatch):
    monkeypatch.setattr(tuning, "DEPTHS", [3])
    monkeypatch.setattr(tuning, "LEAF_SIZES", [2])

    fitted_indexes = []
    real_factory = tuning.make_model

    def recording_factory(depth, leaf_size):
        model = real_factory(depth, leaf_size)
        original_fit = model.fit

        def recording_fit(X, y):
            fitted_indexes.extend(X.index.tolist())
            return original_fit(X, y)

        model.fit = recording_fit
        return model

    monkeypatch.setattr(
        tuning, "make_model", recording_factory
    )

    daily = sample_daily()
    tuning.tune_model(daily)

    # This single-product fixture retains chronological feature indexes.
    assert fitted_indexes

    fitted_dates = daily.loc[fitted_indexes, "date"]

    assert fitted_dates.between(
        "2026-05-01", "2026-08-31"
    ).all()


def test_missing_validation_data_has_clear_error():
    daily = sample_daily()
    daily = daily[
        daily["date"].lt("2026-09-01")
    ].copy()

    with pytest.raises(
        ValueError, match="September validation"
    ):
        tuning.tune_model(daily)


def test_unknown_validation_targets_are_not_scored(small_search):
    daily = sample_daily()

    unknown_day = daily["date"].eq("2026-09-10")
    daily.loc[unknown_day, "daily_units"] = np.nan
    daily.loc[unknown_day, "status"] = "unknown"

    _, _, predictions = tuning.tune_model(daily)

    assert not predictions["date"].eq(
        pd.Timestamp("2026-09-10")
    ).any()

    assert predictions["actual"].notna().all()