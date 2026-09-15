
from pathlib import Path
from typing import Union
import pandas as pd

def load_data(csv_path: Union[str, Path] = Path("data") / "open-meteo-subset.csv") -> pd.DataFrame:
    """Load the local CSV and parse the time column."""
    df = pd.read_csv(csv_path, sep=None, engine="python")
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
    return df

