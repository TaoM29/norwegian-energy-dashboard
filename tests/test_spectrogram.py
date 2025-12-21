import numpy as np
import pandas as pd

from app_core.analysis.spectrogram import production_spectrogram


def _make_df(area="NO1", group="solar", n_hours=24*14):
    idx = pd.date_range("2024-01-01", periods=n_hours, freq="h", tz="UTC")
    x = 10 + 2 * np.sin(2 * np.pi * np.arange(n_hours) / 24.0)
    return pd.DataFrame(
        {
            "price_area": area,
            "production_group": group,
            "start_time": idx,
            "quantity_kwh": x,
        }
    )


def test_production_spectrogram_returns_none_when_no_match():
    df = _make_df(area="NO1", group="solar")
    fig, f, t_idx, Sxx = production_spectrogram(df, area="NO2", group="wind")
    assert fig is None
    assert f is None
    assert t_idx is None
    assert Sxx is None


def test_production_spectrogram_basic_outputs():
    df = _make_df()
    fig, f, t_idx, Sxx = production_spectrogram(
        df,
        area="NO1",
        group="solar",
        window_len=168,
        overlap=84,
        freq_units="cph",
    )
    assert fig is not None
    assert hasattr(fig, "data")
    assert isinstance(f, np.ndarray)
    assert isinstance(Sxx, np.ndarray)
    assert len(t_idx) == Sxx.shape[1]
    assert len(f) == Sxx.shape[0]
    assert len(f) > 0
    assert len(t_idx) > 0


def test_production_spectrogram_fig_y_is_scaled_for_cpd():
    df = _make_df()

    fig_cph, f, _, _ = production_spectrogram(df, window_len=168, overlap=84, freq_units="cph")
    fig_cpd, f2, _, _ = production_spectrogram(df, window_len=168, overlap=84, freq_units="cpd")

    # returned f should always be cycles/hour
    assert np.allclose(f, f2)

    # but the FIG y-axis uses fy:
    y_cph = np.asarray(fig_cph.data[0].y, dtype=float)
    y_cpd = np.asarray(fig_cpd.data[0].y, dtype=float)

    assert np.allclose(y_cph, f)          # cph plot uses raw f
    assert np.allclose(y_cpd, f * 24.0)   # cpd plot uses f*24


def test_production_spectrogram_shapes_are_consistent():
    df = _make_df(n_hours=24*10)
    fig, f, t_idx, Sxx = production_spectrogram(df, window_len=48, overlap=24, freq_units="cph")
    assert fig is not None
    assert Sxx.shape == (len(f), len(t_idx))
