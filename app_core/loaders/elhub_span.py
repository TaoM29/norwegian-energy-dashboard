from __future__ import annotations

from datetime import datetime

import pandas as pd

from app_core.loaders.mongo_utils import load_energy_records


def load_energy_span_df(
    db,
    area: str,
    kind: str,
    group: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Load hourly energy rows for the UTC half-open interval ``[start, end)``.

    The normalized local snapshot is preferred. Passing ``db`` explicitly uses
    the legacy Mongo collections through the same stable record schema.
    Returns DataFrame with columns: time (UTC), quantity_kwh.
    """
    normalized = load_energy_records(
        start=start,
        end=end,
        areas=[area],
        kinds=[kind],
        groups=[group],
        db=db,
    )
    if normalized.empty:
        return pd.DataFrame(columns=["time", "quantity_kwh"])
    return (
        normalized.rename(columns={"timestamp": "time", "value": "quantity_kwh"})
        [["time", "quantity_kwh"]]
        .sort_values("time")
        .reset_index(drop=True)
    )
