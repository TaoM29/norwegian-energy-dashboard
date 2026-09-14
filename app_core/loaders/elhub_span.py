from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

import pandas as pd

from app_core.loaders.mongo_utils import load_energy_records


def energy_collections_for_span(kind: str, start: datetime, end: datetime) -> List[Tuple[str, str]]:
    """
    Return list of (collection_name, group_field) across the year span.
    Handles the legacy production collection split: 2021 vs 2022 onward.
    """
    if pd.Timestamp(start) >= pd.Timestamp(end):
        return []
    final_instant = pd.Timestamp(end) - pd.Timedelta(nanoseconds=1)
    years = range(start.year, final_instant.year + 1)
    out: List[Tuple[str, str]] = []

    if kind == "Production":
        for y in years:
            if y <= 2021:
                out.append(("prod_hour", "production_group"))
            else:
                out.append(("elhub_production_mba_hour", "production_group"))
    elif kind == "Consumption":
        for _y in years:
            out.append(("elhub_consumption_mba_hour", "consumption_group"))
    else:
        raise ValueError("kind must be 'Production' or 'Consumption'")

    # de-dupe preserving order
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


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
