# pages/90_About.py
import streamlit as st

st.set_page_config(page_title="About", layout="wide")
st.title("About this app")

st.markdown("""
This app explores **Norwegian energy production & consumption** (Elhub) and **weather** (Open-Meteo ERA5),
with interactive, Plotly-based visualizations and a shared selection of **price area** and **year**.

### What’s inside
- **Dynamic plots** (Plotly) replacing static matplotlib everywhere.
- **Global selectors** for Area/Year (change them on the *Price Area Selector* page).
- **Caching** and gentle error handling to keep pages responsive.

### Pages
""")

cols = st.columns(2)
with cols[0]:
    st.page_link("pages/02_Price_Area_Selector.py", label="02 · Price Area Selector", icon=":material/tune:")
    st.page_link("pages/10_Energy_Production.py", label="10 · Energy Production", icon=":material/bolt:")
    st.page_link("pages/11_Energy_Consumption.py", label="11 · Energy Consumption", icon=":material/energy_savings_leaf:")

with cols[1]:
    st.page_link("pages/14_Data_Table.py", label="14 · Data Table (Weather)", icon=":material/table_chart:")
    st.page_link("pages/15_Explorer.py", label="15 · Explorer (Weather)", icon=":material/insights:")
    st.page_link("pages/20_Analysis_STL_Spectrogram.py", label="20 · STL & Spectrogram (Production)", icon=":material/analytics:")
    st.page_link("pages/31_SPC_&_LOF.py", label="31 · Data Quality (SPC & LOF)", icon=":material/health_metrics:")

st.markdown("""
### Data sources
- **Elhub** (curated in notebook): `PRODUCTION_PER_GROUP_MBA_HOUR` (2021–2024) and `CONSUMPTION_PER_GROUP_MBA_HOUR` (2021–2024), stored in MongoDB.
- **Open-Meteo ERA5** (hourly weather), loaded on demand.

> Tip: If a page looks stale after data updates, use **Rerun** (⌘/Ctrl-R).
""")