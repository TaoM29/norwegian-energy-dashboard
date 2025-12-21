from __future__ import annotations

import pandas as pd

from app_core.loaders.mongo_utils import get_db, get_prod_coll_for_year


def load_energy_series_hourly(
    area: str,
    kind: str,  # "Production" | "Consumption"
    group: str,
    year: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """
    Fetch hourly energy for one area+group within [start,end] UTC.
    Returns an hourly Series indexed by UTC time (resampled sum).
    """
    if kind not in {"Production", "Consumption"}:
        raise ValueError("kind must be 'Production' or 'Consumption'")

    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")

    if kind == "Production":
        coll = get_prod_coll_for_year(year)
        if coll is None:
            return pd.Series(dtype="float64")

        q = {
            "price_area": area,
            "production_group": group,
            "start_time": {"$gte": start.to_pydatetime(), "$lte": end.to_pydatetime()},
        }
        proj = {"_id": 0, "start_time": 1, "quantity_kwh": 1}
        rows = list(coll.find(q, proj))
        if not rows:
            return pd.Series(dtype="float64")

        d = pd.DataFrame(rows)
        d["start_time"] = pd.to_datetime(d["start_time"], utc=True)
        return (
            d.set_index("start_time")["quantity_kwh"]
            .astype(float)
            .sort_index()
            .resample("h")
            .sum()
        )

    db = get_db()
    coll = db["elhub_consumption_mba_hour"]

    q = {
        "price_area": area,
        "consumption_group": group,
        "start_time": {"$gte": start.to_pydatetime(), "$lte": end.to_pydatetime()},
    }
    proj = {"_id": 0, "start_time": 1, "quantity_kwh": 1}
    rows = list(coll.find(q, proj))
    if not rows:
        return pd.Series(dtype="float64")

    d = pd.DataFrame(rows)
    d["start_time"] = pd.to_datetime(d["start_time"], utc=True)
    return (
        d.set_index("start_time")["quantity_kwh"]
        .astype(float)
        .sort_index()
        .resample("h")
        .sum()
    )
