
# pages/02_Price_Area_Selector.py
import streamlit as st

st.title("Choose Electricity Price Area")
areas = ["NO1","NO2","NO3","NO4","NO5"]
default = st.session_state.get("selected_area", "NO1")
area = st.radio("Price area", areas, index=areas.index(default), horizontal=True)
st.session_state["selected_area"] = area

year = st.number_input("Year (weather / analysis)", 1950, 2100, st.session_state.get("selected_year", 2021), step=1)
st.session_state["selected_year"] = int(year)

st.success(f"Area: **{area}**, Year: **{year}**")
