
import streamlit as st
st.set_page_config(page_title="Modelling — Section", page_icon="📈", layout="wide")

st.markdown(
    "<h1 style='margin-bottom:0'>📈 Modelling</h1>"
    "<p style='opacity:.75;margin-top:.25rem'>Relationships & forecasts</p>"
    "<hr style='margin:1rem 0 1.25rem 0'>",
    unsafe_allow_html=True
)

st.page_link("pages/30_Sliding_Correlation.py", label="Meteorology ↔ Energy — Sliding Window Correlation", icon=":material/stacked_line_chart:")
st.page_link("pages/31_SARIMAX_Forecast.py",    label="Forecasting — SARIMAX (Energy)",                   icon=":material/trending_up:")

st.stop()

