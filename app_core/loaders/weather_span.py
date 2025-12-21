from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd


def load_weather_span_df(
    load_openmeteo_era5: Callable[[str, int], pd.DataFrame],
    area: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Load ERA5 hourly weather for [start,end] by stitching per-year frames.
    Returns DataFrame with a UTC 'time' column.
    """
    frames: list[pd.DataFrame] = []
    for y in range(start.year, end.year + 1):
        w = load_openmeteo_era5(area, y).copy()
        w["time"] = pd.to_datetime(w["time"], utc=True)
        frames.append(w)

    if not frames:
        return pd.DataFrame()

    dfw = pd.concat(frames, ignore_index=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    dfw = dfw[(dfw["time"] >= start_ts) & (dfw["time"] <= end_ts)]
    return dfw.sort_values("time").reset_index(drop=True)
