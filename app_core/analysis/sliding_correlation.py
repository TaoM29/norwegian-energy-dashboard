from __future__ import annotations

import pandas as pd


def apply_lag_hours(x: pd.Series, lag_hours: int) -> pd.Series:
    """
    Positive lag shifts series FORWARD in time: index = index + lag.
    (So weather(t+lag) is compared to energy(t).)
    """
    if x is None or x.empty or int(lag_hours) == 0:
        return x
    out = x.copy()
    out.index = out.index + pd.Timedelta(hours=int(lag_hours))
    return out


def align_two_series(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Intersect indices, reindex, then drop rows where either is NaN."""
    if a is None or b is None or a.empty or b.empty:
        return pd.Series(dtype="float64"), pd.Series(dtype="float64")

    common = a.index.intersection(b.index)
    a2 = a.reindex(common)
    b2 = b.reindex(common)

    mask = a2.notna() & b2.notna()
    return a2[mask], b2[mask]


def rolling_pearson_corr(a: pd.Series, b: pd.Series, window: int, center: bool = True, min_periods: int | None = None) -> pd.Series:
    """
    Rolling Pearson correlation between a and b.
    Default: requires a full window (min_periods=window).
    """
    win = int(window)
    if a is None or b is None or a.empty or b.empty or win <= 1:
        return pd.Series(dtype="float64")

    a2, b2 = align_two_series(a, b)
    if a2.empty:
        return pd.Series(dtype="float64")

    mp = win if min_periods is None else int(min_periods)
    rho = a2.rolling(window=win, min_periods=mp, center=center).corr(b2)
    rho.name = "rolling_corr"
    return rho
