import numpy as np
import pandas as pd
import pytest

import src.evaluate_model as evaluation
from src.features import FEATURE_COLUMNS


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


def selection():
    return {
        "training_end": "2026-08-31",
        "validation_start": "2026-09-01",
        "validation_end": "2026-09-30",
        "test_evaluated": False,
        "feature_columns": list(FEATURE_COLUMNS),
        "selected_settings": {
            "max_depth": 3,
            "min_samples_leaf": 2,
            "n_estimators": 200,
            "random_state": 42,
        },
    }


def test_scores_use_identical_october_rows():
    predictions, per_product, summary = evaluation.evaluate_model(
        sample_daily(),
        selection(),
    )

    assert len(predictions) == 31
    assert predictions["date"].between(
        "2026-10-01",
        "2026-10-31",
    ).all()

    scored = predictions[predictions["scored"]]

    model_mae = (
        scored["actual"] - scored["model_prediction"]
    ).abs().mean()

    baseline_mae = (
        scored["actual"] - scored["baseline_prediction"]
    ).abs().mean()

    assert summary["matched_scored_product_days"] == len(scored)

    assert summary["model_mae_units"] == pytest.approx(
        model_mae
    )

    assert summary["baseline_mae_same_rows"] == pytest.approx(
        baseline_mae
    )

    assert per_product["scored_days"].sum() == len(scored)


def test_refit_excludes_october_targets(monkeypatch):
    fitted_time_features = []
    real_factory = evaluation.make_model

    def recording_factory(depth, leaf_size):
        model = real_factory(depth, leaf_size)
        original_fit = model.fit

        def recording_fit(X, y):
            fitted_time_features.extend(
                X["days_since_start"].tolist()
            )
            return original_fit(X, y)

        model.fit = recording_fit
        return model

    monkeypatch.setattr(
        evaluation,
        "make_model",
        recording_factory,
    )

    evaluation.evaluate_model(
        sample_daily(),
        selection(),
    )

    latest_training_day = (
        pd.Timestamp("2026-09-30")
        - pd.Timestamp("2026-05-01")
    ).days

    assert fitted_time_features
    assert max(fitted_time_features) == latest_training_day


def test_today_and_later_targets_do_not_change_todays_prediction():
    daily = sample_daily()

    before, _, _ = evaluation.evaluate_model(
        daily,
        selection(),
    )

    changed = daily.copy()
    changed.loc[
        changed["date"].ge("2026-10-15"),
        "daily_units",
    ] = 999

    after, _, _ = evaluation.evaluate_model(
        changed,
        selection(),
    )

    before_predictions = before.loc[
        before["date"].le("2026-10-15"),
        "model_prediction",
    ].to_numpy()

    after_predictions = after.loc[
        after["date"].le("2026-10-15"),
        "model_prediction",
    ].to_numpy()

    np.testing.assert_allclose(
        before_predictions,
        after_predictions,
        rtol=1e-12,
        atol=1e-12,
    )


def test_unknown_actual_is_not_scored():
    daily = sample_daily()
    unknown_day = daily["date"].eq("2026-10-10")

    daily.loc[unknown_day, "daily_units"] = np.nan
    daily.loc[unknown_day, "status"] = "unknown"

    predictions, _, _ = evaluation.evaluate_model(
        daily,
        selection(),
    )

    row = predictions[
        predictions["date"].eq(
            pd.Timestamp("2026-10-10")
        )
    ].iloc[0]

    assert pd.notna(row["model_prediction"])
    assert not row["scored"]
    assert pd.isna(row["model_absolute_error"])
    assert pd.isna(row["baseline_absolute_error"])


def test_missing_october_has_clear_error():
    daily = sample_daily()
    daily = daily[
        daily["date"].lt("2026-10-01")
    ].copy()

    with pytest.raises(
        ValueError,
        match="No October rows",
    ):
        evaluation.evaluate_model(
            daily,
            selection(),
        )


def test_invalid_selected_settings_are_rejected():
    invalid = selection()
    invalid["selected_settings"]["min_samples_leaf"] = 999

    with pytest.raises(
        ValueError,
        match="leaf size",
    ):
        evaluation.evaluate_model(
            sample_daily(),
            invalid,
        )


def test_unseen_october_product_has_clear_error():
    daily = sample_daily()

    new_product = daily[
        daily["date"].ge("2026-09-17")
    ].copy()
    new_product["product_id"] = "PRD-NEW"

    # This product has enough history for October features,
    # but no complete feature rows before October.
    # Therefore it is absent from the usable refit data.
    combined = pd.concat(
        [daily, new_product],
        ignore_index=True,
    )

    with pytest.raises(
        ValueError,
        match="Test products without training history: PRD-NEW",
    ):
        evaluation.evaluate_model(
            combined,
            selection(),
        )