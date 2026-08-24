"""Tests for the forecasting pipeline in app.py."""

import numpy as np
import pandas as pd

from app import (
    add_forecasts,
    get_traffic_light_status,
    prepare_weekly_series,
    series_without_forecast,
)

ABWASSER_DATA = "data/Abwassersurveillance_AMELAG/amelag_einzelstandorte.tsv"
WEEK = pd.Timedelta(days=7)


def abwasser_series(standort: str) -> pd.DataFrame:
    """One Klärwerk's measurements, prepared the way the Abwasser tab does it."""
    raw = pd.read_csv(ABWASSER_DATA, sep="\t", parse_dates=["datum"])
    raw = raw[raw["typ"] != "Influenza A+B"].rename(
        columns={"loess_vorhersage": "vorhersage"}
    )
    return raw[raw["standort"] == standort].set_index("datum")


def seasonal_frame(values: np.ndarray, start: str = "2022-01-07") -> pd.DataFrame:
    """A single weekly series on the W-FRI grid, ready for add_forecasts."""
    index = pd.date_range(start, periods=len(values), freq="W-FRI")
    return pd.DataFrame({"y": values, "g": "a"}, index=index)


def test_forecast_is_never_negative_for_real_sites():
    """
    These three sites used to forecast a negative viral load, down to -585808.

    Viral load is never observed below zero, so a forecast below zero is an
    artefact of extrapolating an additive trend.
    """
    for standort in ("Berlin Waßmannsdorf", "Leipzig", "Germersheim"):
        forecasted = add_forecasts(
            abwasser_series(standort), ["vorhersage"], facet_col="typ"
        )
        values = forecasted["vorhersage_forecast"].dropna()
        assert not values.empty, f"no forecast produced for {standort}"
        assert (values >= 0).all(), f"negative forecast for {standort}"


def test_forecast_dates_are_not_thrown_back_to_1970():
    """
    Braunschweig has interior gaps. Dropping those weeks stripped the frequency
    off the index, statsmodels fell back to a RangeIndex and coercing those
    integers to datetimes dated the whole forecast to 1970-01-01.
    """
    frame = abwasser_series("Braunschweig")
    forecasted = add_forecasts(frame, ["vorhersage"], facet_col="typ")
    forecast_rows = forecasted.dropna(subset=["vorhersage_forecast"])

    assert not forecast_rows.empty
    assert forecast_rows.index.min() > pd.Timestamp("2020-01-01")
    assert forecast_rows.index.min() > frame.index.max() - pd.Timedelta(days=30)


def test_forecast_continues_the_weekly_grid():
    """The forecast starts the week after the last observation and stays weekly."""
    values = 1000 + 200 * np.sin(np.arange(160) * 2 * np.pi / 52)
    frame = seasonal_frame(values)

    forecasted = add_forecasts(frame, ["y"], facet_col="g", prediction_horizon=12)
    forecast_rows = forecasted.dropna(subset=["y_forecast"])

    assert len(forecast_rows) == 12
    assert forecast_rows.index.min() == frame.index.max() + WEEK
    assert (forecast_rows.index.to_series().diff().dropna() == WEEK).all()


def test_steeply_declining_series_is_floored_at_zero():
    """The floor, not the model, is what keeps a declining series non-negative."""
    values = np.linspace(10000, 100, 160) + 200 * np.sin(
        np.arange(160) * 2 * np.pi / 52
    )
    frame = seasonal_frame(values)

    floored = add_forecasts(frame, ["y"], facet_col="g")["y_forecast"].dropna()
    unfloored = add_forecasts(frame, ["y"], facet_col="g", non_negative=False)[
        "y_forecast"
    ].dropna()

    assert (floored >= 0).all()
    assert (unfloored < 0).any(), "expected this series to extrapolate below zero"


def test_history_shorter_than_two_seasonal_cycles_is_skipped():
    """
    ExponentialSmoothing needs two full cycles. Asking for a forecast with less
    used to raise inside the loop once per render instead of being skipped.
    """
    frame = seasonal_frame(np.linspace(1, 60, 60))

    forecasted = add_forecasts(frame, ["y"], facet_col="g")

    assert "y_forecast" not in forecasted.columns
    assert series_without_forecast(forecasted, "y", "g") == ["a"]


def test_prepare_weekly_series_keeps_a_contiguous_weekly_grid():
    """Gaps inside the observed span are bridged, not dropped."""
    values = pd.Series(np.linspace(100, 200, 120), index=pd.date_range(
        "2023-01-06", periods=120, freq="W-FRI"))
    values.iloc[40:60] = np.nan  # a 20 week hole, wider than the ffill limit

    weekly = prepare_weekly_series(values, "test", periods=52)

    assert weekly is not None
    assert len(weekly) == 120
    assert not weekly.isna().any()
    assert weekly.index.freq is not None
    assert (weekly.index.to_series().diff().dropna() == WEEK).all()


def test_prepare_weekly_series_rejects_a_mostly_invented_series():
    """A series that is nearly all interpolation is not worth fitting."""
    values = pd.Series(np.linspace(100, 200, 200), index=pd.date_range(
        "2022-01-07", periods=200, freq="W-FRI"))
    values.iloc[20:180] = np.nan

    assert prepare_weekly_series(values, "test", periods=52) is None


def test_traffic_light_marks_a_forecast_derived_value():
    """
    'Aktuelle Lage' falls back to the forecast when observations stop before
    today, and has to say so.
    """
    today = pd.Timestamp.today().normalize()
    observed_index = pd.date_range(end=today - pd.Timedelta(days=21), periods=30,
                                   freq="W-FRI")
    forecast_index = pd.date_range(start=observed_index[-1], periods=5, freq="W-FRI")[1:]
    observed = pd.DataFrame(
        {"y": np.linspace(1, 30, 30), "g": "a"}, index=observed_index
    )
    forecast = pd.DataFrame(
        {"y_forecast": [31.0] * len(forecast_index), "g": "a"}, index=forecast_index
    )

    status = get_traffic_light_status(
        pd.concat([observed, forecast]).sort_index(), "y", facet_col="g"
    )

    assert status["a"]["is_forecast"] is True
    assert status["a"]["date"] in forecast_index


def test_traffic_light_prefers_a_current_observation():
    """With observations up to today the value is not flagged as a forecast."""
    today = pd.Timestamp.today().normalize()
    frame = pd.DataFrame(
        {"y": np.linspace(1, 30, 30), "g": "a"},
        index=pd.date_range(end=today, periods=30, freq="W-FRI"),
    )

    status = get_traffic_light_status(frame, "y", facet_col="g")

    assert status["a"]["is_forecast"] is False


def test_series_without_forecast_names_only_the_missing_ones():
    """One series with a forecast, one without."""
    index = pd.date_range("2024-01-05", periods=4, freq="W-FRI")
    frame = pd.concat([
        pd.DataFrame({"y": [1.0, 2, 3, 4], "y_forecast": [np.nan] * 4, "g": "a"},
                     index=index),
        pd.DataFrame({"y": [np.nan] * 4, "y_forecast": [5.0, 6, 7, 8], "g": "a"},
                     index=index),
        pd.DataFrame({"y": [1.0, 2, 3, 4], "y_forecast": [np.nan] * 4, "g": "b"},
                     index=index),
    ])

    assert series_without_forecast(frame, "y", "g") == ["b"]
