"""Render retained Streamlit pages against tracked CSVs for Phase 0 captures.

Run from the repository root:
    .venv/bin/python -m streamlit run scripts/baseline_streamlit.py
This is a reference harness, not a live-data mode for the public application.
"""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app_core.loaders import elhub_year, mongo_utils, weather


@st.cache_data(show_spinner=False)
def recorded_weather():
    return pd.read_csv(ROOT / "data/open-meteo-subset.csv")


@st.cache_data(show_spinner=False)
def recorded_energy():
    frame = pd.read_csv(ROOT / "data/elhub_prod_by_group_hour_2021.csv")
    frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True)
    return frame


def load_recorded_weather(area, year, **kwargs):
    if area != "Recorded sample (location unknown)" or year != 2020:
        raise ValueError("Weather reference is the recorded 2020 sample only.")
    return recorded_weather().copy()


def load_recorded_energy(db, kind, area, group, year, group_col="production_group", **kwargs):
    if kind != "Production" or year != 2021 or group_col != "production_group":
        raise ValueError("Energy reference supports recorded 2021 production only.")
    frame = recorded_energy()
    return frame.loc[
        (frame["price_area"] == area)
        & (frame["production_group"] == group)
        & (frame["start_time"] >= pd.Timestamp("2021-01-01", tz="UTC"))
        & (frame["start_time"] < pd.Timestamp("2022-01-01", tz="UTC"))
    ].copy()


def deny_network(*args, **kwargs):
    raise RuntimeError("Live network access is disabled in the Phase 0 reference harness.")


st.set_page_config(page_title="Phase 0 — recorded reference", layout="wide")
st.info("PHASE 0 REFERENCE · Recorded CSV inputs · No live data · Original page calculations")

specs = [
    ("01_Home.py", "Home", "home"),
    ("02_Price_Area_Selector.py", "Area & Year", "selector"),
    ("10_Weather_Overview_Stats_and_Sparklines.py", "Weather Overview", "weather-overview"),
    ("11_Weather_Explorer_Multi_Series_and_Resampling.py", "Weather Explorer", "weather-explorer"),
    ("40_STL_Decomposition_and_Spectrogram.py", "STL & Spectrogram", "stl-spectrogram"),
    ("41_SPC_and_LOF_Data_Quality.py", "SPC & LOF", "spc-lof"),
]
pages = [
    st.Page(str(ROOT / "pages" / filename), title=title, url_path=slug, default=slug == "weather-overview")
    for filename, title, slug in specs
]
page = st.navigation({"Recorded reference pages": pages})
if page.url_path == "stl-spectrogram":
    st.session_state["selected_area"] = "NO1"
    st.session_state["selected_year"] = 2021
    st.caption("Recorded Elhub production · NO1 · 2021 UTC slice · final hour absent; source values retained.")
else:
    st.session_state["selected_area"] = "Recorded sample (location unknown)"
    st.session_state["selected_year"] = 2020
    st.caption("Weather CSV · 2020-01-01 to 2020-12-30 · source location/model/unit metadata absent. Labels are inherited, not verified.")

# Original page links are repository-relative; this runner lives in scripts/.
original_page_link = st.page_link

def rooted_page_link(target, **kwargs):
    if isinstance(target, str) and target.startswith("pages/"):
        target = str(ROOT / target)
    # Home also links to uncaptured pages; display their label without enabling live access.
    registered = {str(ROOT / "pages" / filename) for filename, _, _ in specs}
    if isinstance(target, str) and target.startswith(str(ROOT)) and target not in registered:
        return st.caption(kwargs.get("label", Path(target).stem) + " — outside this reference capture")
    return original_page_link(target, **kwargs)


with (
    patch.object(weather, "load_openmeteo_era5", load_recorded_weather),
    patch.object(elhub_year, "load_elhub_year_df", load_recorded_energy),
    patch.object(mongo_utils, "get_db", lambda: None),
    patch("requests.sessions.Session.request", deny_network),
    patch.object(st, "page_link", rooted_page_link),
):
    page.run()
