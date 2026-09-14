import datetime as dt

import pandas as pd
import streamlit as st

from app_core.loaders.mongo_utils import available_years_from_coverage, get_energy_status


PRICE_AREAS = ["NO1", "NO2", "NO3", "NO4", "NO5"]


@st.cache_data(ttl=600, show_spinner=False)
def energy_status() -> dict:
    return get_energy_status()


st.title("Global selection — Price Area & Year")

try:
    status = energy_status()
except Exception as exc:
    st.error(f"Energy coverage could not be loaded: {exc}")
    st.stop()

window = status.get("common_complete_window")
if not status.get("coverage"):
    st.error("No validated energy coverage is available yet.")
    st.stop()

source_latest = pd.Timestamp(status["source_latest_observation"]).tz_convert("UTC")
if window:
    common_start = pd.Timestamp(window["start"]).tz_convert("UTC")
    common_end = pd.Timestamp(window["end"]).tz_convert("UTC")
    common_text = f"{common_start:%Y-%m-%d %H:%M} → {common_end:%Y-%m-%d %H:%M UTC}"
else:
    common_start = common_end = None
    common_text = "not available across every base series"

default_area = st.session_state.get("selected_area", "NO1")
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
    years = available_years_from_coverage(status["coverage"], area=area)
    if not years:
        st.error(f"No validated energy observations are available for {area}.")
        st.stop()
    default_year = int(st.session_state.get("selected_year", years[-1]))
    if default_year not in years:
        default_year = years[-1]
    prior_years = st.session_state.get("selected_years")
    mode = st.segmented_control(
        "Year mode",
        options=["Single year", "Range"],
        default="Single year" if prior_years in (None, [], [default_year]) else "Range",
        key="sel_year_mode",
    )

area_rows = [row for row in status["coverage"] if row["area"] == area and int(row.get("count", 0)) > 0]


def selected_bounds(first_year: int, last_year: int) -> tuple[dt.date, dt.date]:
    requested_start = pd.Timestamp(year=first_year, month=1, day=1, tz="UTC")
    requested_end = pd.Timestamp(year=last_year + 1, month=1, day=1, tz="UTC")
    overlapping = [
        row for row in area_rows
        if pd.Timestamp(row["start"]) < requested_end and pd.Timestamp(row["end"]) > requested_start
    ]
    actual_start = max(requested_start, min(pd.Timestamp(row["start"]) for row in overlapping))
    actual_end = min(requested_end, max(pd.Timestamp(row["end"]) for row in overlapping))
    return actual_start.date(), (actual_end - pd.Timedelta(nanoseconds=1)).date()


if mode == "Single year":
    year = st.selectbox("Year", years, index=years.index(default_year))
    year_start, year_end = selected_bounds(year, year)
    year_list = [year]
else:
    saved = [year for year in (prior_years or []) if year in years]
    default_range = (saved[0], saved[-1]) if saved else (years[0], years[-1])
    y1, y2 = st.select_slider("Year range", options=years, value=default_range)
    year_list = [year for year in years if y1 <= year <= y2]
    year_start, year_end = selected_bounds(y1, y2)

st.session_state["selected_area"] = area
st.session_state["selected_year"] = year_list[-1]
st.session_state["selected_years"] = year_list
st.session_state["selected_start_date"] = year_start
st.session_state["selected_end_date"] = year_end
st.session_state["energy_source_label"] = status["source"]
st.session_state["energy_common_start"] = common_start.isoformat() if common_start is not None else None
st.session_state["energy_common_end"] = common_end.isoformat() if common_end is not None else None
st.session_state["energy_latest_observation"] = source_latest.isoformat()

partial = year_end < dt.date(year_list[-1], 12, 31)
st.caption(
    f"Source: **{status['source']}** · latest source observation: "
    f"**{source_latest:%Y-%m-%d %H:%M UTC}** · all-series common complete window: "
    f"**{common_text}**"
)
st.success(
    f"**Area:** {area}  \n"
    + (f"**Year:** {year_list[-1]}" if len(year_list) == 1 else f"**Years:** {year_list[0]}–{year_list[-1]}")
    + f"  \n**Validated date span:** {year_start.isoformat()} → {year_end.isoformat()}"
    + (" *(partial final year)*" if partial else "")
)

with st.expander("What uses this?"):
    st.markdown(
        """
- Pages read the shared area and validated date span set here.
- Date inputs shown in the app are inclusive. Loaders convert their final date to
  the next UTC midnight so internal queries consistently use `[start, end)`.
- A current year appears only after validated observations exist in the published snapshot.
"""
    )
