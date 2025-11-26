
import streamlit as st
st.set_page_config(page_title="Quality & Diagnostics — Section", page_icon="🧪", layout="wide")

st.markdown(
    "<h1 style='margin-bottom:0'>🧪 Quality & Diagnostics</h1>"
    "<p style='opacity:.75;margin-top:.25rem'>Stats, spectra & anomaly detection</p>"
    "<hr style='margin:1rem 0 1.25rem 0'>",
    unsafe_allow_html=True
)

st.page_link("pages/40_STL_Decomposition_Spectrogram.py", label="Analysis — STL Decomposition & Spectrogram", icon=":material/analytics:")
st.page_link("pages/41_SPC_&_LOF.py",                label="Data Quality — SPC & LOF",    icon=":material/bug_report:")

st.stop()

