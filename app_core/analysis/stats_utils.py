from __future__ import annotations

import numpy as np
import pandas as pd


def zscore(x: pd.Series) -> pd.Series:
    """Z-score a series (safe for empty/constant series)."""
    if x is None or x.empty:
        return x
    v = x.astype(float)
    std = float(v.std(ddof=0))
    if not np.isfinite(std) or std == 0.0:
        return v * 0.0
    return (v - float(v.mean())) / std
