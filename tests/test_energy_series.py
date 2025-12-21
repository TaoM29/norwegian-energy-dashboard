import pandas as pd
import numpy as np
import pytest

import app_core.loaders.energy_series as es


class FakeCollection:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query, proj):
        return list(self._rows)


class FakeDB(dict):
    pass


def test_load_energy_series_invalid_kind_raises():
    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 03:00:00", tz="UTC")
    with pytest.raises(ValueError):
        es.load_energy_series_hourly("NO1", "BadKind", "solar", 2024, start, end)


def test_load_energy_series_localizes_naive_start_end(monkeypatch):
    # production path with one row
    rows = [{"start_time": pd.Timestamp("2024-01-01 00:00:00"), "quantity_kwh": 1.0}]
    monkeypatch.setattr(es, "get_prod_coll_for_year", lambda year: FakeCollection(rows))

    start = pd.Timestamp("2024-01-01 00:00:00")  # naive
    end = pd.Timestamp("2024-01-01 01:00:00")    # naive

    s = es.load_energy_series_hourly("NO1", "Production", "solar", 2024, start, end)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert s.index.tz is not None  # localized / converted to UTC


def test_load_energy_series_production_resample_sum(monkeypatch):
    rows = [
        {"start_time": pd.Timestamp("2024-01-01 00:00:00", tz="UTC"), "quantity_kwh": 1.0},
        {"start_time": pd.Timestamp("2024-01-01 00:30:00", tz="UTC"), "quantity_kwh": 2.0},
        {"start_time": pd.Timestamp("2024-01-01 01:10:00", tz="UTC"), "quantity_kwh": 3.0},
    ]
    monkeypatch.setattr(es, "get_prod_coll_for_year", lambda year: FakeCollection(rows))

    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 02:00:00", tz="UTC")

    s = es.load_energy_series_hourly("NO1", "Production", "solar", 2024, start, end)

    # resample("H").sum(): 00:00 hour has 1+2, 01:00 hour has 3
    assert float(s.loc[pd.Timestamp("2024-01-01 00:00:00", tz="UTC")]) == 3.0
    assert float(s.loc[pd.Timestamp("2024-01-01 01:00:00", tz="UTC")]) == 3.0


def test_load_energy_series_consumption_resample_sum(monkeypatch):
    rows = [
        {"start_time": pd.Timestamp("2024-01-01 00:05:00", tz="UTC"), "quantity_kwh": 1.5},
        {"start_time": pd.Timestamp("2024-01-01 00:50:00", tz="UTC"), "quantity_kwh": 2.5},
        {"start_time": pd.Timestamp("2024-01-01 01:00:00", tz="UTC"), "quantity_kwh": 10.0},
    ]
    fake_db = FakeDB({"elhub_consumption_mba_hour": FakeCollection(rows)})
    monkeypatch.setattr(es, "get_db", lambda: fake_db)

    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 02:00:00", tz="UTC")

    s = es.load_energy_series_hourly("NO1", "Consumption", "household", 2024, start, end)
    assert float(s.loc[pd.Timestamp("2024-01-01 00:00:00", tz="UTC")]) == 4.0
    assert float(s.loc[pd.Timestamp("2024-01-01 01:00:00", tz="UTC")]) == 10.0


def test_load_energy_series_empty_rows_returns_empty(monkeypatch):
    monkeypatch.setattr(es, "get_prod_coll_for_year", lambda year: FakeCollection([]))

    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 01:00:00", tz="UTC")

    s = es.load_energy_series_hourly("NO1", "Production", "solar", 2024, start, end)
    assert isinstance(s, pd.Series)
    assert s.empty
