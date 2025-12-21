import pandas as pd
import numpy as np

from app_core.analysis.stats_utils import zscore


def test_zscore_empty():
    s = pd.Series(dtype=float)
    out = zscore(s)
    assert out.empty


def test_zscore_constant_returns_zeros():
    s = pd.Series([5.0, 5.0, 5.0], index=pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC"))
    out = zscore(s)
    assert np.allclose(out.to_numpy(), 0.0)


def test_zscore_known_values():
    s = pd.Series([0.0, 1.0, 2.0], index=pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC"))
    out = zscore(s)
    # mean=1, std(pop)=sqrt(2/3)
    expected = (s - 1.0) / np.sqrt(2.0/3.0)
    assert np.allclose(out.to_numpy(), expected.to_numpy())
