import numpy as np
import pandas as pd
import pytest

from app_core.analysis import forecast_sarimax as fs


def test_config_bounds_and_daily_defaults():
    c = fs.validate_sarimax_config({"frequency": "D"})
    assert c["baselineLag"] == 7 and c["step"] == 1
    for invalid in ({"horizon": 2000}, {"order": [4, 1, 1]}, {"seasonalOrder": [1, 1, 1, 168]}, {"end": "2024-01-01"}, {"frequency": "D", "energyLagHours": 25}):
        with pytest.raises(ValueError):
            fs.validate_sarimax_config(invalid)


def test_baseline_preserves_missing_clock_hours_and_publication_gap():
    idx = pd.date_range("2025-01-01", periods=72, freq="h", tz="UTC")
    y = pd.Series(np.arange(72, dtype=float), index=idx)
    y.iloc[50] = np.nan
    future = pd.date_range(idx[-1] + pd.Timedelta(hours=25), periods=4, freq="h")
    result = fs._baseline(y, future, 24, "h")
    assert result.iloc[:2].tolist() == [48.0, 49.0]
    assert np.isnan(result.iloc[2])
    assert result.iloc[3] == 51


def test_weather_projection_never_backfills_leading_history():
    idx = pd.date_range("2025-01-01", periods=24, freq="h", tz="UTC")
    weather = pd.DataFrame({"temperature": np.arange(24, dtype=float)}, index=idx)
    target = pd.date_range(idx[0]-pd.Timedelta(hours=1), periods=28, freq="h")
    projected = fs._project_weather(weather, target, "hod-mean", "h")
    assert target[0] not in projected.index
    assert projected.loc[idx[-1]+pd.Timedelta(hours=1), "temperature"] == 0


def test_fit_excludes_weather_not_yet_published(monkeypatch):
    idx = pd.date_range("2025-01-01", periods=72, freq="h", tz="UTC")
    y = pd.Series(np.arange(72, dtype=float), index=idx)
    weather = pd.DataFrame({"temperature": np.arange(72, dtype=float)}, index=idx)
    c = fs.validate_sarimax_config({"dynamic": False, "weatherLagHours": 48})
    seen = []
    class Model:
        def __init__(self, endog, exog, **kwargs):
            self.y = endog
            seen.append(exog.copy())
        def fit(self, **kwargs):
            return self
        aic = 1
        mle_retvals = {"converged": True}
        @property
        def fittedvalues(self):
            return self.y
        def get_forecast(self, steps, exog):
            t = pd.date_range(self.y.index[-1]+pd.Timedelta(hours=1), periods=steps, freq="h")
            self.predicted_mean = pd.Series(1., index=t)
            return self
        def conf_int(self, **kwargs):
            return pd.DataFrame({"lower": self.predicted_mean-1, "upper": self.predicted_mean+1})
    monkeypatch.setattr(fs, "SARIMAX", Model)
    issue = idx[-1]+pd.Timedelta(hours=25)
    fs._fit(y, weather, issue, 4, c)
    weather.loc[idx[48]:] = 1e9
    fs._fit(y, weather, issue, 4, c)
    pd.testing.assert_frame_equal(seen[0], seen[1])
    assert seen[0].iloc[-1,0] == 47
