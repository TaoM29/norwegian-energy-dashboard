
# pages/02_Energy_Production.py
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime

from app_core.loaders.mongo_utils import (
    get_db,
    get_prod_coll_for_year,         
    COLL_PROD_TOTALS_2021,           
)


st.set_page_config(page_title="Elhub – Energy Production", layout="wide")
PAGE = "prod"
YEARS = [2021, 2022, 2023, 2024]

GROUP_COLORS = {
    "hydro":   "#4E79A7",
    "wind":    "#59A14F",
    "solar":   "#EDC948",
    "thermal": "#E15759",
    "nuclear": "#B07AA1",
    "other":   "#BAB0AC",
}


db = get_db()


@st.cache_data(ttl=3600, show_spinner=False)
def _distinct_values():
    """Union of areas/groups across 2021 (old coll) and 2024 (new coll)."""
    c21 = get_prod_coll_for_year(2021)
    c24 = get_prod_coll_for_year(2024)
    areas = sorted(set(c21.distinct("price_area")) | set(c24.distinct("price_area")))
    groups = sorted(set(c21.distinct("production_group")) | set(c24.distinct("production_group")))
    return areas, groups

areas, groups_all = _distinct_values()


@st.cache_data(ttl=600, show_spinner=False)
def get_totals_df(price_area: str, year_: int, groups_key: tuple[str, ...]) -> pd.DataFrame:
    """
    Yearly totals for a price area. For 2021 we prefer precomputed totals if present.
    For 2022–2024 (and 2021 if needed) we aggregate on the fly over start_time.
    """
    if year_ == 2021 and COLL_PROD_TOTALS_2021 in db.list_collection_names():
        docs = list(
            db[COLL_PROD_TOTALS_2021].find({"price_area": price_area}, {"_id": 0})
        )
        df = pd.DataFrame(docs)
        if df.empty:
            return df
        df = df.rename(columns={"production_group": "group", "total_kwh_2021": "kwh"})
        if groups_key:
            df = df[df["group"].isin(groups_key)]
        return df.sort_values("kwh", ascending=False).reset_index(drop=True)

    # Aggregate from hourly collection (2021 if no totals, or any 2022–2024)
    coll = get_prod_coll_for_year(year_)
    start = datetime(year_, 1, 1)
    end   = datetime(year_ + 1, 1, 1)
    match = {"price_area": price_area, "start_time": {"$gte": start, "$lt": end}}
    if groups_key:
        match["production_group"] = {"$in": list(groups_key)}
    pipe = [
        {"$match": match},
        {"$group": {"_id": "$production_group", "kwh": {"$sum": "$quantity_kwh"}}},
        {"$project": {"_id": 0, "group": "$_id", "kwh": 1}},
        {"$sort": {"kwh": -1}},
    ]
    return pd.DataFrame(list(coll.aggregate(pipe, allowDiskUse=True)))

@st.cache_data(ttl=600, show_spinner=False)
def get_hourly_df(price_area: str, year_: int, month_: int, groups_key: tuple[str, ...]) -> pd.DataFrame:
    """Return hourly rows (one month) matching filters."""
    coll  = get_prod_coll_for_year(year_)
    start = datetime(year_, month_, 1)
    end   = datetime(year_ + (month_ == 12), (month_ % 12) + 1, 1)

    match = {"price_area": price_area, "start_time": {"$gte": start, "$lt": end}}
    if groups_key:
        match["production_group"] = {"$in": list(groups_key)}

    rows = list(coll.find(match, {"_id": 0, "production_group": 1, "start_time": 1, "quantity_kwh": 1}))
    if not rows:
        return pd.DataFrame(columns=["production_group", "start_time", "quantity_kwh"])

    df = pd.DataFrame(rows)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df


# UI
st.title("Elhub – Energy Production (2021–2024)")

pa    = st.selectbox("Price area", areas, index=0, key=f"{PAGE}_area")
year  = st.selectbox("Year", YEARS, index=len(YEARS)-1, key=f"{PAGE}_year")
month = st.selectbox("Month (hourly view)", [f"{m:02d}" for m in range(1, 13)], index=0, key=f"{PAGE}_month")

try:
    selected_groups = st.pills(
        "Production groups", groups_all, selection_mode="multi",
        default=groups_all, key=f"{PAGE}_groups",
    )
except Exception:
    selected_groups = st.multiselect("Production groups", groups_all, default=groups_all, key=f"{PAGE}_groups")

groups_key = tuple(sorted(selected_groups)) if selected_groups else tuple()


#  Yearly totals (pie; honors group selection) 
st.subheader(f"Production totals – {pa} – {year}")
df_tot = get_totals_df(pa, year, groups_key)
if df_tot.empty:
    st.info("No totals for this selection.")
else:
    fig = px.pie(
        df_tot, names="group", values="kwh",
        color="group", color_discrete_map=GROUP_COLORS, hole=0.35
    )
    fig.update_traces(sort=False, textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)


# Hourly (line honors group selection) 
st.subheader(f"Hourly production – {pa} – {year}-{month}")
df_hour = get_hourly_df(pa, year, int(month), groups_key)
if df_hour.empty:
    st.info("No hourly rows for this selection.")
else:
    pivot = (
        df_hour.pivot_table(index="start_time", columns="production_group", values="quantity_kwh", aggfunc="sum")
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
- **Source:** Elhub `PRODUCTION_PER_GROUP_MBA_HOUR` (2021 in *prod_hour*, 2022–2024 in *elhub_production_mba_hour*).
- 2021 totals optionally read from **prod_year_totals** (if present); otherwise aggregated on the fly.
- Both charts respect your group selection.
- All timestamps are UTC.
"""
    )

