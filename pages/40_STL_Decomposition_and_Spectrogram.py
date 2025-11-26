
# pages/40_STL_Decomposition_and_Spectrogram.py
from __future__ import annotations

from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_core.loaders.mongo_utils import get_db
from app_core.analysis.stl import stl_decompose_elhub
from app_core.analysis.spectrogram import production_spectrogram  

st.set_page_config(page_title="STL Decomposition & Spectrogram", layout="wide")
st.title("Time-Series Analysis — STL Decomposition & Spectrogram")


# Global selection (from page 02) + tiny link to change it
AREA = st.session_state.get("selected_area", "NO1")
YEAR = int(st.session_state.get("selected_year", 2024))
st.caption(f"Active selection → **Area:** {AREA} • **Year:** {YEAR}")
st.page_link("pages/02_Price_Area_Selector.py", label="Change area/year", icon=":material/settings:")

# Dataset kind + group pickers
colA, colB = st.columns([1.2, 2.5])
with colA:
    KIND = st.radio("Dataset", ["Production", "Consumption"], horizontal=True)

with colB:
    if KIND == "Production":
        groups = ["hydro", "wind", "solar", "thermal", "nuclear", "other"]
        group_key = "stl_group_prod"
        default_index = 2  # solar
        group_col = "production_group"
    else:
        groups = ["household", "cabin", "primary", "secondary", "tertiary", "industry", "private", "business"]
        group_key = "stl_group_cons"
        default_index = 0  # household
        group_col = "consumption_group"

    GROUP = st.selectbox(f"{KIND} group", groups,
                         index=min(default_index, len(groups)-1),
                         key=group_key)


# Parameters
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


# Data loader
@st.cache_data(ttl=900, show_spinner=False)
def load_year_df(kind: str, area: str, group: str, year: int,
                 price_area_col="price_area",
                 group_col="production_group",
                 value_col="quantity_kwh",
                 time_col="start_time") -> pd.DataFrame:
    """
    Fetch one full year's worth of hourly rows for the given dataset (Production/Consumption),
    price area, group and year.
    Collections:
      - Production: 2021 -> prod_hour; 2022–2024 -> elhub_production_mba_hour
      - Consumption: 2021–2024 -> elhub_consumption_mba_hour
    """
    db = get_db()
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)

    if kind == "Production":
        coll_name = "prod_hour" if year == 2021 else "elhub_production_mba_hour"
    else:
        coll_name = "elhub_consumption_mba_hour"

    query = {
        price_area_col: area,
        group_col: group,
        time_col: {"$gte": start, "$lt": end},
    }
    proj = {"_id": 0, price_area_col: 1, group_col: 1, time_col: 1, value_col: 1}

    rows = list(db[coll_name].find(query, proj))
    if not rows:
        return pd.DataFrame(columns=[price_area_col, group_col, time_col, value_col])

    df = pd.DataFrame(rows)
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    df = df.sort_values(time_col).reset_index(drop=True)
    return df

with st.spinner(f"Loading {KIND.lower()} · {AREA} · {GROUP} · {YEAR} …"):
    df_year = load_year_df(KIND, AREA, GROUP, YEAR, group_col=group_col)


# Preview
st.subheader("Data preview")
if df_year.empty:
    st.info(f"No data for **{AREA} / {GROUP} / {YEAR} ({KIND.lower()})**. Try another combination.")
    st.stop()
else:
    span = f"{df_year['start_time'].min()} → {df_year['start_time'].max()}"
    st.caption(f"Rows loaded: **{len(df_year):,}** | span: {span}")
    st.dataframe(df_year.head(30), use_container_width=True, height=280)


# Plots
tabs = st.tabs(["STL", "Spectrogram"])

with tabs[0]:
    if df_year.empty:
        st.stop()

    figs, details, _ = stl_decompose_elhub(
        df_year,
        area=AREA,
        group=GROUP,
        period=int(period_h),
        seasonal=int(seasonal),
        trend=int(trend),
        robust=bool(robust),
        group_col=group_col,
    )

    # --- give the plots more internal bottom space + tidy x-axis ---
    for k in ("observed", "seasonal", "trend", "resid"):
        figs[k].update_layout(margin=dict(t=40, r=10, b=80, l=10))
        figs[k].update_xaxes(tickformat="%Y-%m")  # optional: cleaner monthly ticks

    # --- simple vertical spacer helper ---
    def _spacer(px: int = 28):
        st.markdown(f"<div style='height:{px}px'></div>", unsafe_allow_html=True)

    with st.expander("STL setup (JSON)", expanded=False):
        st.json({**details, "dataset": KIND})

    st.plotly_chart(figs["observed"], use_container_width=True, theme=None)
    _spacer()  # add space between plots
    st.plotly_chart(figs["seasonal"], use_container_width=True, theme=None)
    _spacer()
    st.plotly_chart(figs["trend"], use_container_width=True, theme=None)
    _spacer()
    st.plotly_chart(figs["resid"], use_container_width=True, theme=None)


with tabs[1]:
    fig_sp, *_ = production_spectrogram(
        df_year,
        area=AREA,
        group=GROUP,
        window_len=int(win),
        overlap=int(ovl),
        # pass the correct group_col for either prod or cons
        group_col=group_col,
        # defaults: time_col="start_time", area_col="price_area", value_col="quantity_kwh"
    )
    st.plotly_chart(fig_sp, use_container_width=True, theme=None)

