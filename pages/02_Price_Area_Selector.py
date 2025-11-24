
# pages/02_Price_Area_Selector.py
import streamlit as st
import datetime as dt

# Constants
PRICE_AREAS = ["NO1", "NO2", "NO3", "NO4", "NO5"]
YEARS = [2021, 2022, 2023, 2024]

st.title("Global selection — Area & Year(s)")

# Remember last choice 
default_area = st.session_state.get("selected_area", "NO1")
default_year = st.session_state.get("selected_year", 2024)

left, right = st.columns([1, 1])

with left:
    area = st.radio(
        "Price area",
        PRICE_AREAS,
        index=PRICE_AREAS.index(default_area) if default_area in PRICE_AREAS else 0,
        horizontal=True,
        key="sel_area_radio",
    )

with right:
    mode = st.segmented_control(
        "Year mode",
        options=["Single year", "Range"],
        default="Single year" if st.session_state.get("selected_years") in (None, [], [default_year]) else "Range",
        key="sel_year_mode",
    )

if mode == "Single year":
    year = st.selectbox("Year", YEARS, index=YEARS.index(default_year) if default_year in YEARS else len(YEARS)-1)
    year_start = dt.date(year, 1, 1)
    year_end   = dt.date(year, 12, 31)
    year_list  = [year]
else:
    yr_min, yr_max = min(YEARS), max(YEARS)
    y1, y2 = st.select_slider(
        "Year range",
        options=YEARS,
        value=(
            st.session_state.get("selected_years", [yr_min, yr_max])[0] if st.session_state.get("selected_years") else yr_min,
            st.session_state.get("selected_years", [yr_min, yr_max])[-1] if st.session_state.get("selected_years") else yr_max,
        ),
        help="Applies to pages that support a span (e.g., STL/Spectrogram, correlations, forecasting windows).",
    )
    year_start = dt.date(y1, 1, 1)
    year_end   = dt.date(y2, 12, 31)
    year_list  = list(range(min(y1, y2), max(y1, y2) + 1))

# Persist globally so other pages can read the same state
st.session_state["selected_area"] = area
# Legacy single-year key for older pages:
st.session_state["selected_year"] = year_list[-1]
# New, richer keys:
st.session_state["selected_years"] = year_list
st.session_state["selected_start_date"] = year_start
st.session_state["selected_end_date"] = year_end

# Nice little summary 
st.success(
    f"**Area:** {area}  \n"
    + (f"**Year:** {year_list[-1]}" if len(year_list) == 1 else f"**Years:** {year_list[0]}–{year_list[-1]}")
    + f"  \n**Date span:** {year_start.isoformat()} → {year_end.isoformat()}"
)

with st.expander("What uses this?"):
    st.markdown(
        """
- Pages read `st.session_state["selected_area"]` and **either** `selected_year`
  (for single-year pages) **or** `selected_start_date` / `selected_end_date` (for range-aware pages).
- We keep `selected_year` for backward compatibility, but prefer `selected_years` + start/end dates
  when the page supports multi-year windows (e.g. STL, spectrogram, correlations, forecasting).
"""
    )