
# pages/30_Sliding_Correlation.py
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_core.loaders.weather import load_openmeteo_era5
from app_core.loaders.energy_series import load_energy_series_hourly
from app_core.analysis.stats_utils import zscore
from app_core.analysis.sliding_correlation import (
    apply_lag_hours,
    align_two_series,
    rolling_pearson_corr,
)

# Page setup
st.title("Meteorology ↔ Energy — Sliding Window Correlation")

st.markdown(
    """
**What this shows**

- **Top panel:** the selected **weather variable** and **energy series** aligned hour-by-hour for the chosen month.  
  Turn on *Normalize series* to view both on the same scale (z-score) — this affects **only** the top plot.
- **Lag:** positive values shift **weather forward** in time (tests whether weather **leads** energy by that many hours).
- **Bottom panel:** a **rolling Pearson correlation** (centered window).  
  `r ≈ +1` → move together, `r ≈ −1` → move oppositely, `r ≈ 0` → little linear relationship.
- **Window length:** longer = smoother trend (broader context). Shorter = reacts to local variation (more detail).
- Check the side tab for **Controls**.

*Tip:* Vary the **window length** and try small positive/negative **lags** to compare short-term patterns with longer-term trends.
"""
)

# quick nav back to selector
row = st.columns([1, 6])
with row[0]:
    st.page_link("pages/02_Price_Area_Selector.py", label="Change area/year", icon=":material/settings:")

# global selection (from page 02)
AREA = st.session_state.get("selected_area", "NO1")
YEAR = int(st.session_state.get("selected_year", 2024))
st.caption(f"Active selection → **Area:** {AREA} • **Year:** {YEAR}")

# Controls
with st.sidebar:
    st.header("Controls")

    kind = st.radio("Energy kind", ["Production", "Consumption"], horizontal=False)

    prod_groups = ["hydro", "wind", "solar", "thermal", "nuclear", "other"]
    cons_groups = ["household", "cabin", "primary", "secondary", "tertiary"]
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
    lag_hours = st.slider(
        "Lag (hours) — positive shifts weather forward",
        min_value=-240, max_value=240, value=0, step=1
    )

    normalize_plot = st.toggle("Normalize series for plotting (z-score)", value=True)

    st.caption("Date range is limited to the selected **year** for both series.")
    m = st.selectbox("Month", [f"{m:02d}" for m in range(1, 13)], index=0)

    month_start = pd.Timestamp(f"{YEAR}-{m}-01 00:00:00", tz="UTC")
    month_end = (month_start + pd.offsets.MonthEnd(1)).replace(hour=23, minute=59, second=59)

# Data loaders (Streamlit caching stays in the page)
@st.cache_data(ttl=1800, show_spinner=False)
def load_weather(area: str, year: int) -> pd.DataFrame:
    """Open-Meteo ERA5 for area/year, hourly, UTC."""
    df = load_openmeteo_era5(area, year).copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)

@st.cache_data(ttl=900, show_spinner=False)
def load_energy(area: str, kind: str, group: str, year: int, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Hourly energy (production/consumption) for [start,end]."""
    return load_energy_series_hourly(area=area, kind=kind, group=group, year=year, start=start, end=end)

# Data fetching
with st.spinner("Loading weather…"):
    df_wx = load_weather(AREA, YEAR)

if wx_var not in df_wx.columns:
    st.error(f"Weather variable **{wx_var}** not in weather dataset.")
    st.stop()

wx = (
    df_wx[(df_wx["time"] >= month_start) & (df_wx["time"] <= month_end)]
    .set_index("time")[wx_var]
    .astype(float)
    .resample("H")
    .mean()
)

with st.spinner("Loading energy…"):
    en = load_energy(AREA, kind, group, YEAR, month_start, month_end)

# sanity
if wx.empty:
    st.info("No weather rows for this month/area.")
    st.stop()
if en.empty:
    st.info("No energy rows for this month/area/group.")
    st.stop()

# apply lag + align + corr
wx_lagged = apply_lag_hours(wx, lag_hours)
wx_l, en_l = align_two_series(wx_lagged, en)

if len(wx_l) < max(12, int(window_hours)):
    st.info("Not enough overlapping hourly points for the chosen window. Try a smaller window or a different month.")
    st.stop()

xy = pd.DataFrame({"wx": wx_l.astype(float), "en": en_l.astype(float)})

win = int(window_hours)
rho = rolling_pearson_corr(xy["wx"], xy["en"], window=win, center=True, min_periods=win)

# Plots
wx_plot = zscore(xy["wx"]) if normalize_plot else xy["wx"]
en_plot = zscore(xy["en"]) if normalize_plot else xy["en"]

fig_ts = go.Figure()
fig_ts.add_trace(go.Scatter(
    x=wx_plot.index, y=wx_plot.values,
    name=f"Weather — {wx_var} (lag={lag_hours}h)",
    mode="lines"
))
fig_ts.add_trace(go.Scatter(
    x=en_plot.index, y=en_plot.values,
    name=f"{kind} — {group}",
    mode="lines"
))
fig_ts.update_layout(
    title=f"{AREA} · {YEAR}-{m}  —  Weather vs. {kind.lower()} ({group})",
    xaxis_title="Time (UTC)",
    yaxis_title=("z-score" if normalize_plot else "Value"),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(t=60, r=10, b=10, l=10),
)
st.plotly_chart(fig_ts, use_container_width=True)

fig_rho = go.Figure()
fig_rho.add_trace(go.Scatter(
    x=rho.index, y=rho.values,
    name=f"Rolling corr (win={win}h, lag={lag_hours}h)",
    mode="lines"
))
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

with st.expander("Notes"):
    st.markdown(
        f"""
- **Lag convention:** Positive lag shifts the **weather** series forward in time (i.e., compares weather at *t+lag* to energy at *t*).
- **Window:** Correlation uses a centered rolling window of **{win} hours** and requires a full window.
- **Normalization:** The top plot can optionally show z-scored series for visual comparability only.
- **Data span:** This page reads the selected **month of {YEAR}** only (change month in the sidebar).
        """
    )