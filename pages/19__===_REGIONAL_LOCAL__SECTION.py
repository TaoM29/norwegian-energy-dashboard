
import streamlit as st
st.set_page_config(page_title="Regional & Local — Section", page_icon="🗺️", layout="wide")

st.markdown(
    "<h1 style='margin-bottom:0'>🗺️ Regional & Local</h1>"
    "<p style='opacity:.75;margin-top:.25rem'>Maps & coordinate-driven analysis</p>"
    "<hr style='margin:1rem 0 1.25rem 0'>",
    unsafe_allow_html=True
)

st.page_link("pages/20_Price_Areas_Map_Selector.py", label="Price Areas Map — Choropleth & Click-to-Select", icon=":material/map:")
st.page_link("pages/21_Snow_Drift.py",      label="Snow Drift — Tabler",      icon=":material/ac_unit:")

st.stop()
