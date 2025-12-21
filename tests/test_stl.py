import numpy as np
import pandas as pd

from app_core.analysis.stl import stl_decompose_elhub


def _make_df(area="NO1", group="solar", n_hours=24*14):
    idx = pd.date_range("2024-01-01", periods=n_hours, freq="h", tz="UTC")
    t = np.arange(n_hours, dtype=float)

    # synthetic series: daily seasonality + slight trend
    y = 100.0 + 5.0 * np.sin(2 * np.pi * t / 24.0) + 0.01 * t

    return pd.DataFrame(
        {
            "price_area": area,
            "production_group": group,
            "start_time": idx,
            "quantity_kwh": y,
        }
    )


def test_stl_decompose_returns_error_for_empty():
    df = _make_df(area="NO1", group="solar")
    figs, details, d = stl_decompose_elhub(df, area="NO2", group="wind")
    assert figs == {}
    assert "error" in details
    assert d.empty


def test_stl_decompose_returns_all_figs_and_details():
    df = _make_df()
    figs, details, d = stl_decompose_elhub(
        df,
        area="NO1",
        group="solar",
        period=24,
        seasonal=12,   # even -> should become 13
        trend=364,     # even -> should become 365
        robust=True,
    )

    # figures
    for k in ("observed", "seasonal", "trend", "resid"):
        assert k in figs
        assert figs[k] is not None
        assert hasattr(figs[k], "data")
        assert len(figs[k].data) >= 1

    # details
    assert details["area"] == "NO1"
    assert details["group"] == "solar"
    assert details["period"] == 24
    assert details["seasonal"] % 2 == 1
    assert details["trend"] % 2 == 1
    assert details["n_points"] > 0

    # d: time index should be UTC + sorted
    assert isinstance(d.index, pd.DatetimeIndex)
    assert getattr(d.index, "tz", None) is not None
    assert str(d.index.tz) in ("UTC", "UTC+00:00")
    assert d.index.is_monotonic_increasing


def test_stl_components_lengths_match_observed():
    df = _make_df(n_hours=24*10)

    figs, details, d = stl_decompose_elhub(df, period=24, seasonal=13, trend=365)
    n = details["n_points"]

    # check each plot has n points on its single trace
    for k in ("observed", "seasonal", "trend", "resid"):
        trace = figs[k].data[0]
        assert len(trace.x) == n
        assert len(trace.y) == n
