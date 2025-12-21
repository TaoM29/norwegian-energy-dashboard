import numpy as np
import pandas as pd

import app_core.analysis.sarimax_utils as su


def test_metrics_basic():
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    y = pd.Series([0, 1, 2, 3, 4], index=idx, dtype=float)
    yhat = pd.Series([0, 1, 2, 2, 2], index=idx, dtype=float)

    assert su.mae(y, yhat) == 0.6
    assert round(su.rmse(y, yhat), 6) == round(np.sqrt((0**2 + 0**2 + 0**2 + 1**2 + 2**2)/5), 6)


def test_seasonal_naive_forecast_repeats_last_season():
    idx = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
    y = pd.Series(np.arange(10, dtype=float), index=idx)
    fc = su.seasonal_naive_forecast(y, horizon=6, m=3, freq="h")
    # last 3 values are 7,8,9 -> repeats: 7,8,9,7,8,9
    assert fc.iloc[:6].tolist() == [7.0, 8.0, 9.0, 7.0, 8.0, 9.0]
    assert len(fc) == 6


def test_build_exog_future_last():
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=idx)
    fut = su.build_exog_future(X, horizon=4, freq="h", strategy="last")
    assert fut.shape == (4, 1)
    assert fut["a"].tolist() == [3.0, 3.0, 3.0, 3.0]


def test_aggregate_freq_daily_energy_sum_weather_mean_sum():
    # energy hourly for 2 days: 24 ones each day -> daily sum 24
    t = pd.date_range("2024-01-01", periods=48, freq="h", tz="UTC")
    dfE = pd.DataFrame({"time": t, "quantity_kwh": 1.0})

    dfW = pd.DataFrame({
        "time": t,
        "temperature_2m (°C)": np.linspace(0, 47, 48),
        "precipitation (mm)": np.ones(48),
    })

    eD, wD = su.aggregate_freq(dfE, dfW, "D")
    assert eD["quantity_kwh"].iloc[0] == 24.0
    assert eD["quantity_kwh"].iloc[1] == 24.0
    # precip sums to 24/day
    assert wD["precipitation (mm)"].iloc[0] == 24.0
    # temperature mean should be mean of 0..23 = 11.5 for day1
    assert float(wD["temperature_2m (°C)"].iloc[0]) == 11.5


def test_rolling_backtest_monkeypatched_sarimax_runs():
    # Monkeypatch SARIMAX to keep test fast/deterministic
    class _DummyForecast:
        def __init__(self, idx, val):
            self.predicted_mean = pd.Series([val] * len(idx), index=idx)

    class _DummyRes:
        def __init__(self, endog, freq):
            self._endog = endog
            self._freq = freq

        def get_forecast(self, steps, exog=None):
            start = self._endog.index[-1] + pd.tseries.frequencies.to_offset(self._freq)
            idx = pd.date_range(start, periods=int(steps), freq=self._freq, tz="UTC")
            return _DummyForecast(idx, float(self._endog.iloc[-1]))

    class _DummySARIMAX:
        def __init__(self, endog, exog, order, seasonal_order, enforce_stationarity, enforce_invertibility, freq):
            self._endog = endog
            self._freq = freq

        def fit(self, disp=False):
            return _DummyRes(self._endog, self._freq)

    su.SARIMAX = _DummySARIMAX  # patch in module namespace

    idx = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
    y = pd.Series(np.sin(np.arange(200) / 10.0), index=idx)

    summary, artifacts = su.rolling_origin_backtest_sarimax(
        y_values=y,
        X_values=None,
        freq="H",
        horizon=12,
        step_size=24,
        folds=3,
        m_seasonal=24,
        order=(0, 0, 0),
        seasonal_order=(0, 0, 0, 0),
        eval_no_exog=True,
    )

    assert not summary.empty
    assert "Seasonal naive" in summary["model"].tolist()
    assert "SARIMAX (no exog)" in summary["model"].tolist()
    assert "y_test" in artifacts and "baseline" in artifacts
