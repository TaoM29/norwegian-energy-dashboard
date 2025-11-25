
# pages/01_Home.py
import os
import streamlit as st

st.set_page_config(page_title="Home — IND320 Energy & Weather", layout="wide")

st.title("IND320 — Energy & Weather Dashboard")
st.caption("This app aggregates Elhub production/consumption (2021–2024) and ERA5 weather data.")

st.divider()
st.page_link("pages/02_Price_Area_Selector.py",
             label="Set / Change Area & Year (recommended first step)",
             icon=":material/settings:")

st.divider()

def exists(p: str) -> bool:
    return os.path.exists(p)

def first_existing(*paths):
    for p in paths:
        if exists(p):
            return p
    return None

def safe_link(path, label, icon=""):
    if path:
        st.page_link(path, label=label, icon=icon)


st.subheader("🔎 Exploration")
safe_link(first_existing("pages/10_Data_Table.py"), "Data Table (Weather)", icon=":material/table_chart:")
safe_link(first_existing("pages/11_Explorer.py"), "Explorer", icon=":material/insights:")
safe_link(first_existing("pages/12_Energy_Production.py"), "Energy Production", icon=":material/bolt:")
safe_link(first_existing("pages/13_Energy_Consumption.py"), "Energy Consumption", icon=":material/battery_full:")


st.subheader("🗺️ Regional & Local")
safe_link(first_existing("pages/12_Map_Price_Areas.py", "pages/20_Map_Price_Areas.py"),
           "Map — Price Areas", icon=":material/map:")
safe_link(first_existing("pages/13_Snow_Drift.py", "pages/21_Snow_Drift.py"),
          "Snow Drift (Tabler)", icon=":material/ac_unit:")



st.subheader("📈 Modelling")
safe_link(first_existing("pages/16_Sliding_Correlation.py", "pages/30_Sliding_Correlation.py"),
          "Sliding Correlation", icon=":material/multiline_chart:")
safe_link(first_existing("pages/20_SARIMAX_Forecast.py", "pages/31_SARIMAX_Forecast.py"),
          "SARIMAX Forecast", icon=":material/insights:")



st.subheader("🧪 Quality & Diagnostics")
safe_link(first_existing("pages/20_Analysis_STL_Spectrogram.py", "pages/22_Analysis_STL_Spectrogram.py",
                         "pages/40_Analysis_STL_Spectrogram.py"),
          "STL & Spectrogram (Production)", icon=":material/analytics:")
safe_link(first_existing("pages/31_SPC_&_LOF.py", "pages/41_SPC_&_LOF.py"),
          "Data Quality (SPC / LOF)", icon=":material/bug_report:")

st.divider()
safe_link(first_existing("pages/90_About.py"), "About", icon=":material/info:")

st.caption(
    "Tip: The **Price Area Selector** sets the shared context used by other pages. "
    "You can jump there anytime via the link above."
)