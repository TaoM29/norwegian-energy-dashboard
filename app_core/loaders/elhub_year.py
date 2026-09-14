from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

import pandas as pd

from app_core.loaders.mongo_utils import load_energy_records

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
    UTC-aware half-open ``[start, end)`` range for a full calendar year.
    """
    return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1, tzinfo=timezone.utc)


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
    Fetch one calendar year's available hourly rows using UTC half-open bounds.

    Passing ``db`` explicitly selects the legacy Mongo fallback.
    """
    start, end = year_range_utc(year)
    normalized = load_energy_records(
        start=start,
        end=end,
        areas=[area],
        kinds=[kind],
        groups=[group],
        db=db,
    )
    if normalized.empty:
        return pd.DataFrame(columns=[price_area_col, group_col, time_col, value_col])
    df = normalized.rename(columns={
        "area": price_area_col,
        "group": group_col,
        "timestamp": time_col,
        "value": value_col,
    })[[price_area_col, group_col, time_col, value_col]]
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    return df.sort_values(time_col).reset_index(drop=True)
