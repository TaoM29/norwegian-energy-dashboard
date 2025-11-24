
# pages/20_Analysis_STL_Spectrogram.py
from __future__ import annotations

import pandas as pd
import streamlit as st
from datetime import datetime

from app_core.loaders.mongo_utils import get_prod_coll_for_year
from app_core.analysis.stl import stl_decompose_elhub
from app_core.analysis.spectrogram import production_spectrogram

st.set_page_config(page_title="Analysis — STL & Spectrogram", layout="wide")
st.title("Analysis — STL & Spectrogram (Production)  ↪️")
st.caption("Area and year come from **02 · Price Area Selector**.")

# Quick cache reset
left, _ = st.columns([1, 6])
with left:
    if st.button("Reset caches"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success("Caches cleared. Press ⌘/Ctrl+R to rerun.")


# Global selections (set on 02_Price_Area_Selector.py)
AREA = st.session_state.get("selected_area", "NO1")
YEAR = int(st.session_state.get("selected_year", 2022))

@st.cache_data(ttl=600, show_spinner=False)
def groups_for_year(year: int) -> list[str]:
    """Return available production groups for the selected year (optional nicety)."""
    coll = get_prod_coll_for_year(year)
    if coll is None:
        return ["hydro","wind","solar","thermal","nuclear","other"]
    vals = coll.distinct("production_group") or []
    # keep a consistent order if possible
    order = ["hydro","wind","solar","thermal","nuclear","other"]
    present = [g for g in order if g in vals]
    extras  = [g for g in vals if g not in present]
    return present + extras

group = st.selectbox(
    "Production group",
    groups_for_year(YEAR),
    index=2,
    key="stl_group",
)

# STL params
st.subheader("STL parameters")
p1, p2, p3, p4 = st.columns(4)
with p1:
    period_h = st.number_input("Period (hours)", 1, 2000, 24, step=1)
with p2:
    seasonal = st.number_input("Seasonal (odd)", 3, 9999, 13, step=2)
with p3:
    trend = st.number_input("Trend (odd)", 3, 9999, 365, step=2)
with p4:
    robust = st.toggle("Robust", value=True)

st.subheader("Spectrogram parameters")
q1, q2 = st.columns(2)
with q1:
    win = st.number_input("Window length (hours)", 8, 4096, 168, step=1)
with q2:
    ovl = st.number_input("Overlap (hours)", 0, 4095, 84, step=1)


# Data loader — full year, tied to AREA/YEAR
@st.cache_data(ttl=900, show_spinner=False)
def load_year_df(area: str, group: str, year: int) -> pd.DataFrame:
    """Fetch one full year's hourly rows for a price area+group."""
    coll = get_prod_coll_for_year(year)
    if coll is None:
        return pd.DataFrame(columns=["price_area","production_group","start_time","quantity_kwh"])
    start = datetime(year, 1, 1)
    end   = datetime(year + 1, 1, 1)
    rows = list(coll.find(
        {"price_area": area,
         "production_group": group,
         "start_time": {"$gte": start, "$lt": end}},
        {"_id": 0, "price_area": 1, "production_group": 1, "start_time": 1, "quantity_kwh": 1}
    ))
    if not rows:
        return pd.DataFrame(columns=["price_area","production_group","start_time","quantity_kwh"])
    df = pd.DataFrame(rows)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df.sort_values("start_time").reset_index(drop=True)

with st.spinner(f"Loading {AREA} · {group} · {YEAR} …"):
    df_year = load_year_df(AREA, group, YEAR)

# Preview
st.subheader("Data preview")
if df_year.empty:
    st.info(f"No data for **{AREA} / {group} / {YEAR}**. Try another combination on *02 · Price Area Selector*.")
else:
    span = f"{df_year['start_time'].min()} → {df_year['start_time'].max()}"
    st.caption(f"Rows loaded: **{len(df_year):,}** | span: {span}")
    st.dataframe(df_year.head(30), use_container_width=True, height=280)

# Plots
tabs = st.tabs(["STL (Plotly)", "Spectrogram (Plotly)"])

with tabs[0]:
    if not df_year.empty:
        figs, details, _ = stl_decompose_elhub(
            df_year,
            area=AREA,
            group=group,
            period=int(period_h),
            seasonal=int(seasonal),
            trend=int(trend),
            robust=bool(robust),
        )
        with st.expander("STL setup (JSON)", expanded=False):
            st.json(details)
        st.plotly_chart(figs["observed"], use_container_width=True)
        st.plotly_chart(figs["seasonal"], use_container_width=True)
        st.plotly_chart(figs["trend"],   use_container_width=True)
        st.plotly_chart(figs["resid"],   use_container_width=True)

with tabs[1]:
    if not df_year.empty:
        fig_sp, *_ = production_spectrogram(
            df_year, area=AREA, group=group,
            window_len=int(win), overlap=int(ovl),
        )
        st.plotly_chart(fig_sp, use_container_width=True)

st.caption("Change **Area** or **Year** on the page: *02 · Price Area Selector*.")
