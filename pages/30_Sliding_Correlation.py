
# pages/30_Sliding_Correlation.py
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

from app_core.loaders.weather import load_openmeteo_era5
from app_core.loaders.mongo_utils import get_db, get_prod_coll_for_year

# ---------------- Page setup ----------------
st.set_page_config(page_title="Sliding Window Correlation", layout="wide")
st.title("Meteorology ↔ Energy — Sliding Window Correlation")

# quick nav back to selector
row = st.columns([1, 6])
with row[0]:
    st.page_link("pages/02_Price_Area_Selector.py", label="Change area/year", icon=":material/settings:")

# global selection (from page 02)
AREA = st.session_state.get("selected_area", "NO1")
YEAR = int(st.session_state.get("selected_year", 2024))
st.caption(f"Active selection → **Area:** {AREA} • **Year:** {YEAR}")

# ---------------- Controls ----------------
with st.sidebar:
    st.header("Controls")

    kind = st.radio("Energy kind", ["Production", "Consumption"], horizontal=False)

    prod_groups = ["hydro", "wind", "solar", "thermal", "nuclear", "other"]
    cons_groups = ["household", "cabin", "primary", "secondary", "tertiary", "industry", "private", "business"]
    group = st.selectbox("Energy group", prod_groups if kind == "Production" else cons_groups)

    wx_vars = [
        "temperature_2m (°C)",
        "precipitation (mm)",
        "wind_speed_10m (m/s)",
        "wind_gusts_10m (m/s)",
        "wind_direction_10m (°)",
    ]
    wx_var = st.selectbox("Weather variable", wx_vars, index=0)

    window_hours = st.slider("Window length (hours)", min_value=12, max_value=720, value=168, step=6)
    lag_hours = st.slider("Lag (hours) — positive shifts weather forward", min_value=-240, max_value=240, value=0, step=1)

    normalize_plot = st.toggle("Normalize series for plotting (z-score)", value=True)

    st.caption("Date range is limited to the selected **year** for both series.")
    m = st.selectbox("Month", [f"{m:02d}" for m in range(1, 13)], index=0)
    # in-year month range (full month)
    month_start = pd.Timestamp(f"{YEAR}-{m}-01 00:00:00", tz="UTC")
    month_end = (month_start + pd.offsets.MonthEnd(1)).replace(hour=23, minute=59, second=59)

# ---------------- Data loaders ----------------
@st.cache_data(ttl=1800, show_spinner=False)
def load_weather(area: str, year: int) -> pd.DataFrame:
    """Open-Meteo ERA5 for area/year, hourly, UTC."""
    df = load_openmeteo_era5(area, year).copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)

@st.cache_data(ttl=900, show_spinner=False)
def load_energy_series_production(area: str, group: str, year: int,
                                  start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """
    Fetch hourly production for one area+group within [start, end].
    Uses prod_hour for 2021 and elhub_production_mba_hour for 2022–2024.
    Returns an hourly Series indexed by UTC time.
    """
    coll = get_prod_coll_for_year(year)  # your helper picks correct collection
    if coll is None:
        return pd.Series(dtype="float64")

    q = {
        "price_area": area,
        "production_group": group,
        "start_time": {"$gte": start.to_pydatetime(), "$lte": end.to_pydatetime()},
    }
    proj = {"_id": 0, "start_time": 1, "quantity_kwh": 1}
    rows = list(coll.find(q, proj))
    if not rows:
        return pd.Series(dtype="float64")
    d = pd.DataFrame(rows)
    d["start_time"] = pd.to_datetime(d["start_time"], utc=True)
    s = (
        d.set_index("start_time")["quantity_kwh"]
         .astype(float)
         .sort_index()
         .resample("H")
         .sum()
    )
    return s

@st.cache_data(ttl=900, show_spinner=False)
def load_energy_series_consumption(area: str, group: str, year: int,
                                   start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """
    Fetch hourly consumption for one area+group within [start, end] (2021–2024).
    Collection: elhub_consumption_mba_hour.
    """
    db = get_db()
    coll = db["elhub_consumption_mba_hour"]

    q = {
        "price_area": area,
        "consumption_group": group,
        "start_time": {"$gte": start.to_pydatetime(), "$lte": end.to_pydatetime()},
    }
    proj = {"_id": 0, "start_time": 1, "quantity_kwh": 1}
    rows = list(coll.find(q, proj))
    if not rows:
        return pd.Series(dtype="float64")
    d = pd.DataFrame(rows)
    d["start_time"] = pd.to_datetime(d["start_time"], utc=True)
    s = (
        d.set_index("start_time")["quantity_kwh"]
         .astype(float)
         .sort_index()
         .resample("H")
         .sum()
    )
    return s

def zscore(x: pd.Series) -> pd.Series:
    if x.empty:
        return x
    v = x.astype(float)
    std = v.std(ddof=0)
    return (v - v.mean()) / std if std and not np.isnan(std) and std != 0.0 else v * 0.0

# ---------------- Fetch & align data ----------------
with st.spinner("Loading weather…"):
    df_wx = load_weather(AREA, YEAR)

if wx_var not in df_wx.columns:
    st.error(f"Weather variable **{wx_var}** not in weather dataset.")
    st.stop()

# slice to selected month
wx = (
    df_wx[(df_wx["time"] >= month_start) & (df_wx["time"] <= month_end)]
        .set_index("time")[wx_var]
        .astype(float)
        .resample("H")
        .mean()
)

with st.spinner("Loading energy…"):
    if kind == "Production":
        en = load_energy_series_production(AREA, group, YEAR, month_start, month_end)
    else:
        en = load_energy_series_consumption(AREA, group, YEAR, month_start, month_end)

# sanity
if wx.empty:
    st.info("No weather rows for this month/area.")
    st.stop()
if en.empty:
    st.info("No energy rows for this month/area/group.")
    st.stop()

# apply lag (positive = shift weather forward)
if lag_hours != 0:
    wx_lagged = wx.copy()
    wx_lagged.index = wx_lagged.index + pd.Timedelta(hours=lag_hours)
else:
    wx_lagged = wx

# intersect time index
common_idx = wx_lagged.index.intersection(en.index)
wx_l = wx_lagged.reindex(common_idx)
en_l = en.reindex(common_idx)

# drop missing
mask = wx_l.notna() & en_l.notna()
wx_l = wx_l[mask]
en_l = en_l[mask]

if len(wx_l) < max(12, window_hours):
    st.info("Not enough overlapping hourly points for the chosen window. Try a smaller window or a different month.")
    st.stop()

# build 2-column DataFrame for correlation
xy = pd.DataFrame({"wx": wx_l.astype(float), "en": en_l.astype(float)})

# rolling correlation (centered); use pandas built-in corr between two Series
win = int(window_hours)
minp = win  # require full window
rho = xy["wx"].rolling(window=win, min_periods=minp, center=True).corr(xy["en"])
rho.name = "rolling_corr"

# ---------------- Plots ----------------
# Top plot: the two series (optionally z-scored)
wx_plot = zscore(xy["wx"]) if normalize_plot else xy["wx"]
en_plot = zscore(xy["en"]) if normalize_plot else xy["en"]

fig_ts = go.Figure()
fig_ts.add_trace(go.Scatter(x=wx_plot.index, y=wx_plot.values,
                            name=f"Weather — {wx_var} (lag={lag_hours}h)",
                            mode="lines"))
fig_ts.add_trace(go.Scatter(x=en_plot.index, y=en_plot.values,
                            name=f"{kind} — {group}",
                            mode="lines"))
fig_ts.update_layout(
    title=f"{AREA} · {YEAR}-{m}  —  Weather vs. {kind.lower()} ({group})",
    xaxis_title="Time (UTC)",
    yaxis_title=("z-score" if normalize_plot else "Value"),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(t=60, r=10, b=10, l=10),
)
st.plotly_chart(fig_ts, use_container_width=True)

# Bottom plot: rolling correlation
fig_rho = go.Figure()
fig_rho.add_trace(go.Scatter(x=rho.index, y=rho.values,
                             name=f"Rolling corr (win={win}h, lag={lag_hours}h)",
                             mode="lines"))
fig_rho.add_hline(y=0.0, line_width=1, line_dash="dot", line_color="gray")
fig_rho.update_layout(
    title="Sliding Correlation",
    xaxis_title="Time (UTC)",
    yaxis_title="Pearson r",
    yaxis_range=[-1.05, 1.05],
    hovermode="x unified",
    margin=dict(t=50, r=10, b=10, l=10),
)
st.plotly_chart(fig_rho, use_container_width=True)


# ---------------- Notes ----------------
with st.expander("Notes"):
    st.markdown(
        f"""
- **Lag convention:** Positive lag shifts the **weather** series forward in time (i.e., compares weather at *t+lag* to energy at *t*).
- **Window:** Correlation uses a centered rolling window of **{win} hours** and requires a full window.
- **Normalization:** The top plot can optionally show z-scored series for visual comparability only.
- **Data span:** This page reads the selected **month of {YEAR}** only (change month in the sidebar).
        """
    )