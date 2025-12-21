from datetime import datetime
import pandas as pd

from app_core.loaders.elhub_span import load_energy_span_df


class FakeCollection:
    def __init__(self, rows):
        self._rows = rows

    def aggregate(self, pipe, allowDiskUse=False):
        return self._rows


class FakeDB(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


def test_load_energy_span_df_stitches_and_utc():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 1, 2, 0, 0)

    rows = [
        {"start_time": datetime(2024, 1, 1, 0), "quantity_kwh": 1.0},
        {"start_time": datetime(2024, 1, 1, 1), "quantity_kwh": 2.0},
        {"start_time": datetime(2024, 1, 1, 2), "quantity_kwh": 3.0},
    ]

    db = FakeDB({
        "elhub_production_mba_hour": FakeCollection(rows),
    })

    df = load_energy_span_df(db=db, area="NO1", kind="Production", group="solar", start=start, end=end)
    assert list(df.columns) == ["time", "quantity_kwh"]
    assert len(df) == 3
    assert isinstance(df["time"].dtype, pd.DatetimeTZDtype)
    assert str(df["time"].dtype.tz) == "UTC"