
# pages/40_STL_Decomposition_and_Spectrogram.py
from __future__ import annotations

from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_core.loaders.mongo_utils import get_db
from app_core.analysis.stl import stl_decompose_elhub
from app_core.loaders.elhub_year import load_elhub_year_df
from app_core.analysis.spectrogram import production_spectrogram  


st.title("Time-Series Analysis — STL Decomposition & Spectrogram")

st.markdown(
    """
**What this page does**

- Loads one full year of **hourly energy** for the selected **price area** and **group** (production or consumption).
- Lets you explore the time-series using two complementary tools:
  - **STL decomposition** (trend/seasonality/residual)
  - **Spectrogram** (how periodic patterns change over time)

**STL (Seasonal-Trend decomposition using LOESS)**

- Splits the series into:
  - **Observed** (the original signal)
  - **Seasonal** (repeating pattern with the chosen period)
  - **Trend** (slow-moving long-term changes)
  - **Residual** (what remains: noise + anomalies not explained by trend/seasonality)
- Key controls:
  - **Period (hours):** the expected repeating cycle (e.g. 24 for daily, 168 for weekly).
  - **Seasonal / Trend (odd):** smoothing window sizes (must be odd; the UI enforces this).
  - **Robust:** reduces influence of outliers when fitting (often a good default).

**Spectrogram (frequency content over time)**

- Computes a time–frequency heatmap using a sliding window:
  - Brighter areas = stronger repeating behavior at that frequency.
  - Helps reveal shifts like “daily pattern stronger in summer” or “weekly rhythm fades”.
- Key controls:
  - **Window length (hours):** longer = better frequency resolution but less time detail.
  - **Overlap (hours):** more overlap = smoother spectrogram but heavier computation.

**How to read it**

- If **Trend** moves but **Seasonal** stays stable → long-term shift with same rhythm.
- If **Seasonal** changes shape/amplitude → changing daily/weekly behavior.
- Large spikes in **Residual** or isolated hot spots in the spectrogram can hint at unusual events.

Check the controls above to switch dataset/group and tune STL/spectrogram parameters.
"""
)


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
        groups = ["household", "cabin", "primary", "secondary", "tertiary"]
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
def load_year_df_cached(kind: str, area: str, group: str, year: int, group_col: str) -> pd.DataFrame:
    db = get_db()
    return load_elhub_year_df(
        db=db,
        kind=kind,
        area=area,
        group=group,
        year=year,
        group_col=group_col,
    )


with st.spinner(f"Loading {KIND.lower()} · {AREA} · {GROUP} · {YEAR} …"):
    df_year = load_year_df_cached(KIND, AREA, GROUP, YEAR, group_col=group_col)


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

    # give the plots more internal bottom space + tidy x-axis 
    for k in ("observed", "seasonal", "trend", "resid"):
        figs[k].update_layout(margin=dict(t=40, r=10, b=80, l=10))
        figs[k].update_xaxes(tickformat="%Y-%m")  


    # helper to add space between plots
    def _spacer(px: int = 28):
        st.markdown(f"<div style='height:{px}px'></div>", unsafe_allow_html=True)

    with st.expander("STL setup (JSON)", expanded=False):
        st.json({**details, "dataset": KIND})

    st.plotly_chart(figs["observed"], use_container_width=True, theme=None)
    _spacer()  
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
        group_col=group_col,
    )
    st.plotly_chart(fig_sp, use_container_width=True, theme=None)

