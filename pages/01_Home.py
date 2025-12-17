
# pages/01_Home.py
import os
import streamlit as st


st.title("Energy & Weather Dashboard")
st.caption("Interactive exploration of Elhub production/consumption (2021–2024) and Open-Meteo ERA5 weather.")


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
- **Energy:** Elhub hourly **production/consumption** by group, NO1–NO5, **2021–2024** (stored in MongoDB).
- **Weather:** ERA5 hourly (Open-Meteo API), fetched on demand; **UTC** timestamps.
- **Resampling:** Means by default; precipitation often uses **sum** (see page-specific notes).
- **Missing values:** Small gaps are occasionally interpolated (time-based) for analysis stability and spectrogram/STL windows.
- **Shared selection:** Area & year set on the **Price Area Selector** page; most pages read these from `st.session_state`.
"""
)

with st.expander("Under the hood / performance", expanded=False):
    st.markdown(
        """
- **Plotting:** Plotly throughout; Folium for mapping.
- **Analysis:** Statsmodels (STL, SARIMAX), scikit-learn (LOF), SciPy (spectrogram).
- **DB:** MongoDB collections for 2021 and 2022–2024 harmonized in loaders.
- **Caching:** `st.cache_data` keeps API/DB calls snappy; clear with the page’s *Reset cache* button where available.
- **Repro tips:** When changing area/year or parameters, use **Rerun** (⌘/Ctrl-R) if something looks stale.
        """
    )

st.caption(
    "Tip: The **Price Area Selector** sets the shared context used by other pages. "
    "You can jump there anytime via the link near the top of this page."
)