
# pages/03_Energy_Consumption.py
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime

from app_core.loaders.mongo_utils import get_db

st.set_page_config(page_title="Elhub – Energy Consumption", layout="wide")
PAGE = "cons"
YEARS = [2021, 2022, 2023, 2024]

# Full expected set – we will union this with Mongo distinct values
DEFAULT_CONS_GROUPS = [
    "household", "cabin", "primary", "secondary",
    "tertiary", "industry", "private", "business",
]

GROUP_COLORS = {
    "household": "#4E79A7",
    "cabin":     "#F28E2B",
    "primary":   "#59A14F",
    "secondary": "#E15759",
    "tertiary":  "#B07AA1",
    "industry":  "#76B7B2",
    "private":   "#EDC948",
    "business":  "#BAB0AC",
}

# controls / helpers 
left, _ = st.columns([1,3])
with left:
    if st.button("Reset caches", key=f"{PAGE}_reset"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success("Caches cleared — press Rerun")

db = get_db()
coll = db["elhub_consumption_mba_hour"]


@st.cache_data(ttl=3600, show_spinner=False)
def _distinct_values():
    areas = sorted(coll.distinct("price_area"))
    # union Mongo values with the full default list (lower-cased)
    mongo_groups = [g for g in coll.distinct("consumption_group") if isinstance(g, str)]
    groups = sorted(set(DEFAULT_CONS_GROUPS) | set(g.strip().lower() for g in mongo_groups))
    return areas, groups


@st.cache_data(ttl=600, show_spinner=False)
def totals_df(price_area: str, year_: int, groups_key: tuple[str, ...]) -> pd.DataFrame:
    start = datetime(year_, 1, 1); end = datetime(year_ + 1, 1, 1)
    match = {"price_area": price_area, "start_time": {"$gte": start, "$lt": end}}
    if groups_key:
        match["consumption_group"] = {"$in": list(groups_key)}
    pipe = [
        {"$match": match},
        {"$group": {"_id": "$consumption_group", "kwh": {"$sum": "$quantity_kwh"}}},
        {"$project": {"_id": 0, "group": "$_id", "kwh": 1}},
        {"$sort": {"kwh": -1}},
    ]
    return pd.DataFrame(list(coll.aggregate(pipe, allowDiskUse=True)))


@st.cache_data(ttl=600, show_spinner=False)
def hourly_df(price_area: str, year_: int, month_: int, groups_key: tuple[str, ...]) -> pd.DataFrame:
    start = datetime(year_, month_, 1)
    end   = datetime(year_ + (month_ == 12), (month_ % 12) + 1, 1)
    match = {"price_area": price_area, "start_time": {"$gte": start, "$lt": end}}
    if groups_key:
        match["consumption_group"] = {"$in": list(groups_key)}
    rows = list(coll.find(
        match, {"_id": 0, "consumption_group": 1, "start_time": 1, "quantity_kwh": 1}
    ))
    if not rows:
        return pd.DataFrame(columns=["consumption_group", "start_time", "quantity_kwh"])
    df = pd.DataFrame(rows)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df


# UI 
st.title("Elhub – Energy Consumption (2021–2024)")

areas, groups_all = _distinct_values()
pa    = st.selectbox("Price area", areas or ["NO1","NO2","NO3","NO4","NO5"], index=0, key=f"{PAGE}_area")
year  = st.selectbox("Year", YEARS, index=len(YEARS)-1, key=f"{PAGE}_year")
month = st.selectbox("Month (hourly view)", [f"{m:02d}" for m in range(1, 13)], index=0, key=f"{PAGE}_month")

try:
    selected_groups = st.pills(
        "Consumption groups", groups_all, selection_mode="multi",
        default=groups_all, key=f"{PAGE}_groups",
    )
except Exception:
    selected_groups = st.multiselect(
        "Consumption groups", groups_all, default=groups_all, key=f"{PAGE}_groups"
    )

groups_key = tuple(sorted(selected_groups)) if selected_groups else tuple()


# Yearly totals 
st.subheader(f"Consumption totals – {pa} – {year}")
df_tot = totals_df(pa, year, groups_key)
if df_tot.empty:
    st.info("No totals for this selection.")
else:
    fig = px.pie(
        df_tot, names="group", values="kwh",
        color="group", color_discrete_map=GROUP_COLORS, hole=0.35
    )
    fig.update_traces(sort=False, textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)


# Hourly 
st.subheader(f"Hourly consumption – {pa} – {year}-{month}")
df_hour = hourly_df(pa, year, int(month), groups_key)
if df_hour.empty:
    st.info("No hourly rows for this selection.")
else:
    pivot = (
        df_hour.pivot_table(index="start_time", columns="consumption_group", values="quantity_kwh", aggfunc="sum")
        .sort_index()
    )
    if selected_groups:
        pivot = pivot[[c for c in pivot.columns if c in selected_groups]]
    fig2 = px.line(
        pivot, x=pivot.index, y=pivot.columns,
        labels={"value": "kWh", "start_time": "Time (UTC)"},
        color_discrete_map=GROUP_COLORS,
    )
    fig2.update_layout(legend_title_text="Group")
    st.plotly_chart(fig2, use_container_width=True)

with st.expander("Data & implementation notes"):
    st.markdown(
        """
- **Source:** Elhub `CONSUMPTION_PER_GROUP_MBA_HOUR` (2021–2024 in *elhub_consumption_mba_hour*).
- Group selectors are the union of Mongo distinct values and the full expected set  
  (`household, cabin, primary, secondary, tertiary, industry, private, business`).
- Both charts respect your group selection. Timestamps are UTC.
"""
    )