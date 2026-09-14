
# pages/01_Home.py
import os
import pandas as pd
import streamlit as st

from app_core.loaders.mongo_utils import get_energy_status


st.title("Energy & Weather Dashboard")
st.caption("Interactive exploration of validated Elhub production/consumption and Open-Meteo ERA5-Seamless weather.")

try:
    energy_status = get_energy_status()
    common = energy_status.get("common_complete_window")
    if common:
        st.caption(
            f"Energy source: **{energy_status['source']}** · latest source observation: "
            f"**{pd.Timestamp(energy_status['source_latest_observation']):%Y-%m-%d %H:%M UTC}** · "
            f"common complete through **{pd.Timestamp(common['last_observation']):%Y-%m-%d %H:%M UTC}**"
        )
except Exception:
    pass


# Primary CTA
st.divider()
st.page_link(
    "pages/02_Price_Area_Selector.py",
    label="Set / Change Area & Year (recommended first step)",
    icon=":material/settings:",
)
st.divider()

# small helpers for robust links
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


# What you can do here
st.markdown(
    """
### What this app helps you do
- **Explore** hourly weather and energy series with dynamic Plotly charts.
- **Map** Norwegian price areas (NO1–NO5), click to select a coordinate, and color areas by aggregated production/consumption.
- **Analyze** time series structure (STL) and frequency content (spectrogram).
- **Assess quality** with SPC-style outlier bands and LOF anomalies.
- **Model** relationships (sliding window correlation) and **forecast** (SARIMAX) with optional weather exogenous variables.
"""
)

with st.expander("Quick start", expanded=True):
    st.markdown(
        """
1) Go to **Price Area Selector** and choose *area + year* (shared across the app).  
2) Browse **Exploration** pages to understand seasonal/diurnal patterns.  
3) Open **Map** to click a location; then compute **Snow Drift** for that point.  
4) Use **Sliding Correlation** to see how weather ↔ energy relationships change over time.  
5) Try **SARIMAX** to forecast production/consumption; add weather as exogenous regressors and compare runs.
        """
    )


# Link blocks
st.subheader("🔎 Exploration")
safe_link(first_existing("pages/10_Weather_Overview_Stats_and_Sparklines.py"), "Weather Overview - Stats & Sparklines", icon=":material/table_chart:")
safe_link(first_existing("pages/11_Weather_Explorer_Multi_Series_and_Resampling.py"), "Weather Explorer - Multi-Series & Resampling", icon=":material/insights:")
safe_link(first_existing("pages/12_Energy_Production.py"),"Energy Production Hourly and Totals", icon=":material/bolt:")
safe_link(first_existing("pages/13_Energy_Consumption.py"),"Energy Consumption Hourly and Totals", icon=":material/battery_full:")


st.subheader("🗺️ Regional & Local")
safe_link(first_existing("pages/20_Price_Areas_Map_Selector.py"), "Price Areas Map - Click-to-Select", icon=":material/map:")
safe_link(first_existing("pages/21_Snow_Drift.py"), "Snow Drift (Tabler)", icon=":material/ac_unit:")


st.subheader("📈 Modelling")
safe_link(first_existing("pages/30_Sliding_Correlation.py"), "Sliding Correlation", icon=":material/multiline_chart:")
safe_link(first_existing("pages/31_SARIMAX_Forecast.py"),"SARIMAX Forecast (with exogenous weather)", icon=":material/insights:")


st.subheader("🧪 Quality & Diagnostics")
safe_link(first_existing("pages/40_STL_Decomposition_and_Spectrogram.py"), "Time-Series Analysis — STL Decomposition & Spectrogram", icon=":material/analytics:")
safe_link(first_existing("pages/41_SPC_and_LOF_Data_Quality.py"), "Data Quality — SPC (Outliers) & LOF (Anomalies)", icon=":material/bug_report:")


st.divider()
safe_link(first_existing("pages/99_About.py", "pages/90_About.py"), "About", icon=":material/info:")


# Data & assumptions
st.markdown(
    """
### Data & assumptions
- **Energy:** Elhub hourly **production/consumption** by group, NO1–NO5, from the validated local snapshot when available.
- **Weather:** ERA5-Seamless hourly (Open-Meteo API), expected about five days after observation; pages show actual coverage and **UTC** timestamps.
- **Resampling:** Means by default; precipitation often uses **sum** (see page-specific notes).
- **Missing values:** Missing energy is kept missing. Analyses that require a complete hourly series report gaps instead of replacing them with zero.
- **Shared selection:** Area & year set on the **Price Area Selector** page; most pages read these from `st.session_state`.
"""
)

with st.expander("Under the hood / performance", expanded=False):
    st.markdown(
        """
- **Plotting:** Plotly throughout; Folium for mapping.
- **Analysis:** Statsmodels (STL, SARIMAX), scikit-learn (LOF), SciPy (spectrogram).
- **Storage:** The local validated SQLite snapshot is preferred; MongoDB remains a compatibility fallback.
- **Caching:** `st.cache_data` keeps API/DB calls snappy; clear with the page’s *Reset cache* button where available.
- **Repro tips:** When changing area/year or parameters, use **Rerun** (⌘/Ctrl-R) if something looks stale.
        """
    )

st.caption(
    "Tip: The **Price Area Selector** sets the shared context used by other pages. "
    "You can jump there anytime via the link near the top of this page."
)
