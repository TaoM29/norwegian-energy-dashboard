from pathlib import Path
import pandas as pd

from app_core.loaders.data_io import load_data


def test_load_data_parses_time_column(tmp_path: Path):
    p = tmp_path / "sample.csv"
    p.write_text("time,value\n2024-01-01 00:00:00,1\n2024-01-01 01:00:00,2\n", encoding="utf-8")

    df = load_data(p)

    assert list(df.columns) == ["time", "value"]
    assert pd.api.types.is_datetime64_any_dtype(df["time"])
    assert df["value"].tolist() == [1, 2]


def test_load_data_works_without_time_column(tmp_path: Path):
    p = tmp_path / "sample.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    df = load_data(p)

    assert list(df.columns) == ["a", "b"]
    assert df.shape == (2, 2)
