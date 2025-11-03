
# pages/01_Home.py
import streamlit as st
from weather_loader import load_openmeteo_era5

st.title("Dashboard Basics – Weather Data")
st.caption("Use the sidebar to navigate between pages.")

# area/year set on page 2
area = st.session_state.get("selected_area", "NO1")
year = st.session_state.get("selected_year", 2021)

df = load_openmeteo_era5(area, year)

st.subheader("Quick preview of data")
st.dataframe(df.head(20), use_container_width=True)

st.sidebar.caption("Data is cached for speed.")

