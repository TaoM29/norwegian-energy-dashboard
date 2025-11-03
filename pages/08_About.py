
#pages/07_About.py
import streamlit as st

st.title("About")
st.markdown(
    "- Weather now loads from the **Open-Meteo ERA5 API** (no CSV)\n"
    "- Page order: 1, 4, NEW A, 2, 3, NEW B, 5\n"
    "- NEW A: **STL** & **Spectrogram** (production)\n"
    "- NEW B: **DCT/SPC** & **LOF** (weather)\n"
    "Change area/year on page 2 and revisit pages to see updates."
)

