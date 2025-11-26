
import streamlit as st
st.set_page_config(page_title="Exploration — Section", page_icon="🔎", layout="wide")

st.markdown(
    "<h1 style='margin-bottom:0'>🔎 Exploration</h1>"
    "<p style='opacity:.75;margin-top:.25rem'>Data browsing & quick looks</p>"
    "<hr style='margin:1rem 0 1.25rem 0'>",
    unsafe_allow_html=True
)

c1, c2 = st.columns(2)
with c1:
    st.page_link("pages/10_Weather_Overview_Stats_and_Sparklines.py", label="Weather Overview - Stats & Sparklines", icon=":material/table_chart:")
    st.page_link("pages/11_Weather_Explorer_Multi_Series_and_Resampling.py", label="Weather Explorer — Multi-Series & Resampling", icon=":material/insights:")
with c2:
    st.page_link("pages/12_Energy_Production.py",  label="Energy Production",   icon=":material/bolt:")
    st.page_link("pages/13_Energy_Consumption.py", label="Energy Consumption",  icon=":material/battery_full:")
st.stop()


