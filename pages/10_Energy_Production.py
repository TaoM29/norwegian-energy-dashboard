
# pages/10_Energy_Production.py
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime
from app_core.loaders.mongo_utils import (
    get_db, get_prod_coll_for_year, COLL_PROD_TOTALS_2021
)


# global scope from selector 
def require_area_year():
    area = st.session_state.get("selected_area")
    year = st.session_state.get("selected_year")
    if area is None or year is None:
        st.warning("Please choose a price area and year on the **Price Area Selector** page first.")
        st.page_link("pages/02_Price_Area_Selector.py", label="Open selector", icon=":material/tune:")
        st.stop()
    return str(area), int(year)

AREA, YEAR = require_area_year()
st.caption(f"Scope: **{AREA}**, **{YEAR}**")
st.page_link("pages/02_Price_Area_Selector.py", label="Change selection", icon=":material/settings:")

st.title("Energy Production (2021–2024)")

GROUP_COLORS = {
    "hydro": "#4E79A7", "wind": "#59A14F", "solar": "#EDC948",
    "thermal": "#E15759", "nuclear": "#B07AA1", "other": "#BAB0AC",
}


db = get_db()


@st.cache_data(ttl=1800, show_spinner=False)
def all_groups() -> list[str]:
    # union of groups across years we have
    g = set()
    for y in (2021, 2022, 2023, 2024):
        try:
            g |= set(get_prod_coll_for_year(y).distinct("production_group"))
        except Exception:
            pass
    return sorted(g)


@st.cache_data(ttl=600, show_spinner=False)
def totals_df(area: str, year_: int, groups: tuple[str, ...]) -> pd.DataFrame:
    # 2021 may have precomputed totals
    if year_ == 2021 and COLL_PROD_TOTALS_2021 in db.list_collection_names():
        cur = db[COLL_PROD_TOTALS_2021].find({"price_area": area}, {"_id": 0})
        df = pd.DataFrame(list(cur)).rename(columns={"total_kwh_2021": "total_kwh"})
        if groups:
            df = df[df["production_group"].isin(groups)]
        df = df.sort_values("total_kwh", ascending=False)
        return df[["production_group", "total_kwh"]]

    # on the fly for other years
    coll = get_prod_coll_for_year(year_)
    match = {"price_area": area, "year": year_}
    if groups:
        match["production_group"] = {"$in": list(groups)}
    pipe = [
        {"$match": match},
        {"$group": {"_id": "$production_group", "total_kwh": {"$sum": "$quantity_kwh"}}},
        {"$project": {"_id": 0, "production_group": "$_id", "total_kwh": 1}},
        {"$sort": {"total_kwh": -1}},
    ]
    return pd.DataFrame(list(coll.aggregate(pipe, allowDiskUse=True)))


@st.cache_data(ttl=600, show_spinner=False)
def hourly_df(area: str, year_: int, month_: int, groups: tuple[str, ...]) -> pd.DataFrame:
    coll = get_prod_coll_for_year(year_)
    start = datetime(year_, month_, 1)
    end   = datetime(year_ + (month_ == 12), (month_ % 12) + 1, 1)
    match = {"price_area": area, "start_time": {"$gte": start, "$lt": end}}
    if groups:
        match["production_group"] = {"$in": list(groups)}
    rows = list(coll.find(match, {"_id": 0, "production_group": 1, "start_time": 1, "quantity_kwh": 1}))
    if not rows:
        return pd.DataFrame(columns=["production_group", "start_time", "quantity_kwh"])
    df = pd.DataFrame(rows)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df


# UI controls (NO area/year pickers here!)
groups_all = all_groups()
month_label = st.selectbox("Month (hourly view)", [f"{m:02d}" for m in range(1, 13)], index=0)
selected_groups = st.multiselect("Production groups", groups_all, default=groups_all)
groups_key = tuple(sorted(selected_groups)) if selected_groups else tuple()


# Totals pie
df_tot = totals_df(AREA, YEAR, groups_key)
st.subheader(f"Totals — {AREA} — {YEAR}")
if df_tot.empty:
    st.info("No totals for this selection.")
else:
    fig = px.pie(
        df_tot, names="production_group", values="total_kwh",
        color="production_group", color_discrete_map=GROUP_COLORS, hole=0.35
    )
    st.plotly_chart(fig, use_container_width=True)


# Hourly lines
df_hour = hourly_df(AREA, YEAR, int(month_label), groups_key)
st.subheader(f"Hourly — {AREA} — {YEAR}-{month_label}")
if df_hour.empty:
    st.info("No hourly rows for this selection.")
else:
    pivot = (
        df_hour.pivot_table(index="start_time", columns="production_group",
                            values="quantity_kwh", aggfunc="sum")
        .sort_index()
    )
    if selected_groups:
        pivot = pivot[[c for c in pivot.columns if c in selected_groups]]
    fig2 = px.line(
        pivot, x=pivot.index, y=pivot.columns,
        labels={"value": "kWh", "start_time": "Time (UTC)"},
        color_discrete_map=GROUP_COLORS
    )
    st.plotly_chart(fig2, use_container_width=True)

