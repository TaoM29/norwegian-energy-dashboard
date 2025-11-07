
from pathlib import Path
from typing import Union
import pandas as pd
import streamlit as st

@st.cache_data(show_spinner=False)
def load_data(csv_path: Union[str, Path] = Path("data") / "open-meteo-subset.csv") -> pd.DataFrame:
    """Load the local CSV and parse the time column. Cached for speed."""
    df = pd.read_csv(csv_path, sep=None, engine="python")
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
    return df

