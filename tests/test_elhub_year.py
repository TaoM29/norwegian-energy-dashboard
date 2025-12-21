from datetime import datetime
import pandas as pd
from pandas import DatetimeTZDtype

from app_core.loaders.elhub_year import collection_name_for, year_range_utc, load_elhub_year_df


class FakeCollection:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query, proj):
        return self._rows


class FakeDB(dict):
    pass


def test_collection_name_for():
    assert collection_name_for("Production", 2021) == "prod_hour"
    assert collection_name_for("Production", 2024) == "elhub_production_mba_hour"
    assert collection_name_for("Consumption", 2021) == "elhub_consumption_mba_hour"
    assert collection_name_for("Consumption", 2024) == "elhub_consumption_mba_hour"


def test_year_range_utc():
    start, end = year_range_utc(2024)
    assert start == datetime(2024, 1, 1)
    assert end == datetime(2025, 1, 1)


def test_load_elhub_year_df_empty():
    db = FakeDB()
    db["prod_hour"] = FakeCollection(rows=[])

    df = load_elhub_year_df(db, "Production", "NO1", "solar", 2021)
    assert df.empty
    assert list(df.columns) == ["price_area", "production_group", "start_time", "quantity_kwh"]


def test_load_elhub_year_df_rows_sorted_and_utc():
    db = FakeDB()
    rows = [
        {"price_area": "NO1", "production_group": "solar", "start_time": datetime(2024, 1, 1, 1), "quantity_kwh": 2.0},
        {"price_area": "NO1", "production_group": "solar", "start_time": datetime(2024, 1, 1, 0), "quantity_kwh": 1.0},
    ]
    db["elhub_production_mba_hour"] = FakeCollection(rows=rows)

    df = load_elhub_year_df(db, "Production", "NO1", "solar", 2024)

    assert len(df) == 2
    assert isinstance(df["start_time"].dtype, DatetimeTZDtype)
    assert df["start_time"].iloc[0] < df["start_time"].iloc[1]
    assert df["quantity_kwh"].tolist() == [1.0, 2.0]
