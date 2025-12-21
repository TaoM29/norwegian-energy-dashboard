from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

import pandas as pd

Kind = Literal["Production", "Consumption"]


def collection_name_for(kind: Kind, year: int) -> str:
    """
    Map (kind, year) -> Mongo collection name.
    """
    if kind == "Production":
        return "prod_hour" if year == 2021 else "elhub_production_mba_hour"
    return "elhub_consumption_mba_hour"


def year_range_utc(year: int) -> tuple[datetime, datetime]:
    """
    [start, end) range for a full calendar year in naive datetime (Mongo stores naive datetimes).
    """
    return datetime(year, 1, 1), datetime(year + 1, 1, 1)


def load_elhub_year_df(
    db,
    kind: Kind,
    area: str,
    group: str,
    year: int,
    *,
    price_area_col: str = "price_area",
    group_col: str = "production_group",
    value_col: str = "quantity_kwh",
    time_col: str = "start_time",
) -> pd.DataFrame:
    """
    Fetch one full year's worth of hourly rows for (kind, area, group, year).
    db is a pymongo database handle (or a fake in unit tests).
    """
    start, end = year_range_utc(year)
    coll_name = collection_name_for(kind, year)

    query = {
        price_area_col: area,
        group_col: group,
        time_col: {"$gte": start, "$lt": end},
    }
    proj = {"_id": 0, price_area_col: 1, group_col: 1, time_col: 1, value_col: 1}

    rows = list(db[coll_name].find(query, proj))
    if not rows:
        return pd.DataFrame(columns=[price_area_col, group_col, time_col, value_col])

    df = pd.DataFrame(rows)
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    return df.sort_values(time_col).reset_index(drop=True)
