
# pages/99_About.py
import streamlit as st

st.set_page_config(page_title="About", layout="wide")
st.title("About this app")

st.markdown(
    """
This app explores **Norwegian energy production & consumption** (Elhub) together with **weather** (ERA5 via Open-Meteo).  
It uses a shared selection of **Price Area** and **Year** (set on *Price Area Selector*) and interactive Plotly visuals throughout.
The app is built with Streamlit + Plotly. All times are shown in UTC.
"""
)

st.divider()


# How to use (quick start)
st.subheader("How to use (quick start)")
st.markdown(
    """
1. Open **Price Area Selector** to choose the active **area** (NO1–NO5) and **year**.  
2. Browse the pages below—your selection is used everywhere.
"""
)


# Quick links grouped like the sidebar 
st.subheader("Quick links")

c1, c2 = st.columns(2)

with c1:
    st.caption("Overview")
    st.page_link("pages/01_Home.py", label="Home", icon=":material/home:")
    st.page_link("pages/02_Price_Area_Selector.py", label="Price Area Selector", icon=":material/tune:")

    st.caption("Exploration")
    st.page_link("pages/10_Weather_Overview_Stats_and_Sparklines.py", label="Weather Overview - Stats & Sparklines", icon=":material/table_chart:")
    st.page_link("pages/11_Weather_Explorer_Multi_Series_and_Resampling.py", label="Weather Explorer - Multi-Series & Resampling", icon=":material/insights:")
    st.page_link("pages/12_Energy_Production.py", label="Energy Production", icon=":material/bolt:")
    st.page_link("pages/13_Energy_Consumption.py", label="Energy Consumption", icon=":material/battery_full:")


with c2:
    st.caption("Regional & Local")
    st.page_link("pages/20_Price_Areas_Map_Selector.py", label="Price Areas Map - Click-to-Select", icon=":material/map:")
    st.page_link("pages/21_Snow_Drift.py", label="Snow Drift (Tabler)", icon=":material/ac_unit:")

    st.caption("Modelling")
    st.page_link("pages/30_Sliding_Correlation.py", label="Sliding Correlation (Weather ↔ Energy)", icon=":material/show_chart:")
    st.page_link("pages/31_SARIMAX_Forecast.py", label="SARIMAX Forecast (with exogenous weather)", icon=":material/monitoring:")

    st.caption("Quality & Diagnostics")
    st.page_link("pages/40_STL_Decomposition_and_Spectrogram.py", label="Time-Series Analysis — STL Decomposition & Spectrogram", icon=":material/analytics:")
    st.page_link("pages/41_SPC_and_LOF_Data_Quality.py", label="Data Quality — SPC (Outliers) & LOF (Anomalies)", icon=":material/health_metrics:")


st.divider()


# Data sources / tech notes 
st.subheader("Data sources")
st.markdown(
    """
- **Elhub**: hourly production (*PRODUCTION_PER_GROUP_MBA_HOUR*) for 2021–2024 and hourly consumption (*CONSUMPTION_PER_GROUP_MBA_HOUR*) for 2021–2024.  
  Data are curated in the notebooks and stored in **MongoDB** for the app.
- **Open-Meteo ERA5**: hourly weather (temperature, precipitation, wind speed/gust/direction). Requested on-demand and cached in the app.

> Tip: If a view looks stale after changing inputs, use **Rerun** (⌘/Ctrl-R).
"""
)


# Project links & author
st.subheader("Project links")
st.markdown(
    """
- 🧑‍💻 **GitHub repo:** https://github.com/TaoM29/IND320-dashboard-basics
"""
)

st.caption("Design & implementation by **Taofik Muhriz**.")

