# app.py
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="IND320 – Energy & Weather", page_icon="📊", layout="wide")

pages: dict[str, list] = {}

# Helper to add pages
def add(section: str, path: str, title: str, icon: str):
    if Path(path).exists():
        pages.setdefault(section, []).append(st.Page(path, title=title, icon=icon))


# Overview
add("Overview", "pages/01_Home.py", "Home", ":material/home:")
add("Overview", "pages/02_Price_Area_Selector.py", "Area & Year", ":material/settings:")
add("Overview", "pages/99_About.py", "About", ":material/info:")


# Exploration
add("Exploration", "pages/10_Weather_Overview_Stats_and_Sparklines.py", "Weather Overview", ":material/table_chart:")
add("Exploration", "pages/11_Weather_Explorer_Multi_Series_and_Resampling.py", "Weather Explorer", ":material/insights:")
add("Exploration", "pages/12_Energy_Production.py", "Energy Production", ":material/bolt:")
add("Exploration", "pages/13_Energy_Consumption.py", "Energy Consumption", ":material/battery_full:")


# Regional & Local
add("Regional & Local", "pages/20_Price_Areas_Map_Selector.py", "Price Areas Map", ":material/map:")
add("Regional & Local", "pages/21_Snow_Drift.py", "Snow Drift", ":material/ac_unit:")


# Modelling
add("Modelling", "pages/30_Sliding_Correlation.py", "Sliding Correlation", ":material/multiline_chart:")
add("Modelling", "pages/31_SARIMAX_Forecast.py", "SARIMAX Forecast", ":material/insights:")


# Quality & Diagnostics
add("Quality & Diagnostics", "pages/40_STL_Decomposition_and_Spectrogram.py", "STL & Spectrogram", ":material/analytics:")
add("Quality & Diagnostics", "pages/41_SPC_and_LOF_Data_Quality.py", "SPC & LOF", ":material/bug_report:")


pg = st.navigation(pages, position="sidebar", expanded=True)
pg.run()





