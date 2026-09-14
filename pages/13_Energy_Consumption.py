from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from app_core.loaders.energy_series import matched_ytd_summary, matched_ytd_windows
from app_core.loaders.mongo_utils import available_years_from_coverage, get_energy_status, load_energy_records


GROUP_COLORS = {
    "household": "#4E79A7", "cabin": "#59A14F", "primary": "#EDC948",
    "secondary": "#E15759", "tertiary": "#B07AA1",
}


@st.cache_data(ttl=600, show_spinner=False)
def load_year(area: str, year: int) -> pd.DataFrame:
    return load_energy_records(
        start=datetime(year, 1, 1, tzinfo=timezone.utc),
        end=datetime(year + 1, 1, 1, tzinfo=timezone.utc),
        areas=[area], kinds=["consumption"],
    )


AREA = str(st.session_state.get("selected_area", "NO1"))
STATUS = get_energy_status()
available_years = available_years_from_coverage(STATUS["coverage"], area=AREA, kinds=["consumption"])
if not available_years:
    st.error("No validated common energy coverage is available.")
    st.stop()
YEAR = int(st.session_state.get("selected_year", available_years[-1]))
YEAR = YEAR if YEAR in available_years else available_years[-1]
st.title("Energy Consumption — Consumption Groups Overview")
st.page_link("pages/02_Price_Area_Selector.py", label="Change selection", icon=":material/settings:")

with st.spinner("Loading validated energy data…"):
    frame = load_year(AREA, YEAR)

if frame.empty:
    st.info(f"No validated consumption data is available for {AREA} in {YEAR}.")
    st.stop()

base_groups = {"household", "cabin", "primary", "secondary", "tertiary"}
available_groups = sorted(set(frame["group"]) & base_groups)
selected_groups = st.multiselect("Consumption groups", available_groups, default=available_groups)
if not selected_groups:
    st.info("Select at least one consumption group.")
    st.stop()
frame = frame[frame["group"].isin(selected_groups)].copy()

comparison = None
comparison_windows = None
year_end_exclusive = pd.Timestamp(year=YEAR + 1, month=1, day=1, tz="UTC")
selected_coverage = [
    row for row in STATUS["coverage"]
    if row["area"] == AREA and row["kind"] == "consumption" and row["group"] in selected_groups
    and pd.Timestamp(row["start"]) < year_end_exclusive
    and pd.Timestamp(row["end"]) > pd.Timestamp(year=YEAR, month=1, day=1, tz="UTC")
]
common_cutoff = min(
    [year_end_exclusive, *[pd.Timestamp(row["end"]) for row in selected_coverage]]
)
if YEAR == available_years[-1] and YEAR - 1 in available_years and common_cutoff < year_end_exclusive:
    comparison_windows = matched_ytd_windows(YEAR, common_cutoff)
    prior_frame = load_year(AREA, YEAR - 1)
    prior_frame = prior_frame[prior_frame["group"].isin(selected_groups)].copy()
    comparison = matched_ytd_summary(
        frame, prior_frame, windows=comparison_windows, groups=selected_groups,
    )
    frame = frame[frame["timestamp"] < comparison_windows["current_end"]].copy()

available_months = sorted(frame["timestamp"].dt.month.unique())
month = st.selectbox(
    "Month (hourly view)", available_months,
    index=len(available_months) - 1 if YEAR == datetime.now(timezone.utc).year else 0,
    format_func=lambda value: f"{value:02d}",
)

first = frame["timestamp"].min()
last = frame["timestamp"].max()
partial = common_cutoff < year_end_exclusive
period_suffix = " YTD" if partial and YEAR == datetime.now(timezone.utc).year else (" (partial period)" if partial else "")
st.caption(
    f"Scope: **{AREA}, {YEAR}**{' (partial)' if partial else ''} · "
    f"observations: **{first:%Y-%m-%d %H:%M} → {last:%Y-%m-%d %H:%M UTC}** · "
    f"source: **{STATUS['source']}**"
)

if comparison is not None:
    totals = (comparison[["group", "current_kwh"]]
              .rename(columns={"group": "consumption_group", "current_kwh": "total_kwh"})
              .sort_values("total_kwh", ascending=False))
else:
    totals = (frame.groupby("group", as_index=False)["value"].sum(min_count=1)
              .rename(columns={"group": "consumption_group", "value": "total_kwh"})
              .sort_values("total_kwh", ascending=False))
st.subheader(f"Totals — {AREA} — {YEAR}{period_suffix}")
fig = px.pie(
    totals, names="consumption_group", values="total_kwh",
    color="consumption_group", color_discrete_map=GROUP_COLORS, hole=0.35,
)
st.plotly_chart(fig, use_container_width=True)

if comparison is not None and comparison_windows is not None:
    st.subheader(f"Matched YTD comparison — {YEAR} vs {YEAR - 1}")
    complete = comparison[comparison["is_comparable"]]
    if len(complete) == len(comparison) and complete["prior_kwh"].sum() != 0:
        current_total = float(complete["current_kwh"].sum())
        prior_total = float(complete["prior_kwh"].sum())
        st.metric(
            f"Total through {(comparison_windows['current_end'] - pd.Timedelta(hours=1)):%Y-%m-%d %H:%M UTC}",
            f"{current_total:,.0f} kWh",
            f"{(current_total / prior_total - 1) * 100:+.1f}% vs matched {YEAR - 1}",
        )
    else:
        st.info("Some selected groups do not have complete hourly coverage in both matched periods; their change is left blank.")
    st.dataframe(
        comparison.rename(columns={
            "group": "Consumption group", "current_kwh": f"{YEAR} YTD kWh",
            "prior_kwh": f"{YEAR - 1} matched kWh", "change_pct": "Change (%)",
            "current_hours": f"{YEAR} hours", "prior_hours": f"{YEAR - 1} hours",
            "expected_hours": "Expected hours", "is_comparable": "Comparable",
        }),
        hide_index=True, use_container_width=True,
    )

hourly = frame[frame["timestamp"].dt.month == month]
pivot = hourly.pivot_table(
    index="timestamp", columns="group", values="value", aggfunc=lambda values: values.sum(min_count=1),
).sort_index()
st.subheader(f"Hourly — {AREA} — {YEAR}-{month:02d}")
st.plotly_chart(
    px.line(
        pivot, x=pivot.index, y=pivot.columns,
        labels={"value": "kWh", "timestamp": "Time (UTC)"},
        color_discrete_map=GROUP_COLORS,
    ),
    use_container_width=True,
)
