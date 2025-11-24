
# app.py 
import streamlit as st

st.set_page_config(page_title="IND320 – Project App", page_icon="📊", layout="wide")

st.markdown("# IND320 – Energy & Weather 📊")
st.caption("Elhub production/consumption (2021–2024) + ERA5 weather.")

st.divider()
st.page_link("pages/02_Price_Area_Selector.py",
             label="Set / Change Area & Year (recommended first step)",
             icon=":material/settings:")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Exploration & Data")
    st.page_link("pages/10_Energy_Production.py", label="10 · Energy Production", icon=":material/bolt:")
    st.page_link("pages/11_Energy_Consumption.py", label="11 · Energy Consumption", icon=":material/battery_full:")
    st.page_link("pages/14_Data_Table.py", label="14 · Data Table (Weather)", icon=":material/table_chart:")
    st.page_link("pages/15_Explorer.py", label="15 · Explorer", icon=":material/insights:")

with right:
    st.subheader("Analysis & Quality")
    st.page_link("pages/20_Analysis_STL_Spectrogram.py", label="20 · STL & Spectrogram", icon=":material/analytics:")
    st.page_link("pages/31_SPC_&_LOF.py", label="31 · Data Quality (SPC / LOF)", icon=":material/bug_report:")
    st.page_link("pages/90_About.py", label="90 · About", icon=":material/info:")

st.divider()
st.caption(
    "Tip: The **Price Area Selector** sets the shared context used by other pages. "
    "You can jump there anytime via the link above."
)

# ------------------------------------------------------------------
# Helpful links & notes
# ------------------------------------------------------------------
st.markdown(
    """
**Project links**
- 🌐 App (Cloud): https://ind320-project-work-nonewthing.streamlit.app
- 🧑‍💻 Repo: https://github.com/TaoM29/IND320-dashboard-basics
"""
)





