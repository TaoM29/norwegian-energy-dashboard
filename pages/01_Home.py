
# pages/01_Home.py
import streamlit as st

st.set_page_config(page_title="Home — IND320 Energy & Weather", layout="wide")

st.title("IND320 — Energy & Weather Dashboard")
st.caption("This app aggregates Elhub production/consumption (2021–2024) and ERA5 weather data.")

# Keep Home page neutral — no area/year echo here.

st.markdown("""
### What you’ll find
- **Price Area Selector** — Pick the price area and analysis year used across the app.
- **Energy Production & Consumption** — Interactive Plotly views (hourly + totals).
- **Weather Data Table** — Stats + sparklines, plus a flexible interactive chart.
- **Explorer** — Multi-series Plotly exploration with month range and resampling.
- **Analysis** — STL decomposition and Spectrogram for production.
- **Data Quality** — DCT/SPC outliers and LOF anomalies for weather.

Use the links below to jump straight in.
""")

st.divider()
st.subheader("Quick links")

col1, col2, col3 = st.columns(3)

with col1:
    st.page_link("pages/02_Price_Area_Selector.py", label="02 · Price Area Selector", icon=":material/settings:")
    st.page_link("pages/10_Energy_Production.py", label="10 · Energy Production", icon=":material/bolt:")
    st.page_link("pages/11_Energy_Consumption.py", label="11 · Energy Consumption", icon=":material/battery_full:")

with col2:
    st.page_link("pages/14_Data_Table.py", label="14 · Data Table (Weather)", icon=":material/table_chart:")
    st.page_link("pages/15_Explorer.py", label="15 · Explorer", icon=":material/insights:")

with col3:
    st.page_link("pages/20_Analysis_STL_Spectrogram.py", label="20 · STL & Spectrogram", icon=":material/analytics:")
    st.page_link("pages/31_SPC_&_LOF.py", label="31 · Data Quality (SPC/LOF)", icon=":material/bug_report:")
    st.page_link("pages/90_About.py", label="90 · About", icon=":material/info:")