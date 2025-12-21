from datetime import datetime
import pandas as pd

from app_core.loaders.weather_span import load_weather_span_df


def test_load_weather_span_df_slices():
    def fake_loader(area: str, year: int) -> pd.DataFrame:
        t = pd.date_range(f"{year}-01-01", periods=5, freq="h", tz="UTC")
        return pd.DataFrame({"time": t, "temperature_2m (°C)": range(5)})

    start = datetime(2024, 1, 1, 1)
    end = datetime(2024, 1, 1, 3)

    df = load_weather_span_df(load_openmeteo_era5=fake_loader, area="NO1", start=start, end=end)
    assert len(df) == 3
    assert df["time"].min() == pd.Timestamp("2024-01-01 01:00:00", tz="UTC")
    assert df["time"].max() == pd.Timestamp("2024-01-01 03:00:00", tz="UTC")
