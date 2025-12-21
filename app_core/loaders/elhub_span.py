from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

import pandas as pd


def energy_collections_for_span(kind: str, start: datetime, end: datetime) -> List[Tuple[str, str]]:
    """
    Return list of (collection_name, group_field) across the year span.
    Handles production collection split: 2021 vs 2022–2024.
    """
    years = range(start.year, end.year + 1)
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
    Load hourly energy rows for [start,end] (inclusive) across collections.
    Returns DataFrame with columns: time (UTC), quantity_kwh.
    """
    colls = energy_collections_for_span(kind, start, end)

    frames: list[pd.DataFrame] = []
    for coll_name, group_field in colls:
        pipe = [
            {
                "$match": {
                    "price_area": area,
                    group_field: group,
                    "start_time": {"$gte": start, "$lte": end},
                }
            },
            {"$project": {"_id": 0, "start_time": 1, "quantity_kwh": 1}},
        ]
        rows = list(db[coll_name].aggregate(pipe, allowDiskUse=True))
        if rows:
            frames.append(pd.DataFrame(rows))

    if not frames:
        return pd.DataFrame(columns=["time", "quantity_kwh"])

    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["start_time"], utc=True)
    df = df[["time", "quantity_kwh"]].sort_values("time").reset_index(drop=True)

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return df[(df["time"] >= start_ts) & (df["time"] <= end_ts)]
