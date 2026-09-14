
# pages/21_Snow_Drift.py
from __future__ import annotations

import math
from datetime import date
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from app_core.loaders.weather import era5_available_end, load_openmeteo_point


# Page setup
st.title("Snow Drift — Tabler")

# Coordinate from Map page
clicked = st.session_state.get("clicked_coord")
if not clicked:
    st.info(
        "No coordinate selected yet. Open **Price Areas Map — Click-to-Select**, click on the map, "
        "then return here.",
        icon="🗺️",
    )
    st.page_link("pages/20_Price_Areas_Map_Selector.py", label="Go to Map page", icon=":material/map:")
    st.stop()

lat, lon = float(clicked[0]), float(clicked[1])
st.caption(f"Using coordinate from Map page → **({lat:.5f}, {lon:.5f})**")


# Defaults for Tabler parameters 
DEFAULT_T = 3000       # maximum transport distance [m]
DEFAULT_F = 30000      # fetch distance [m]
DEFAULT_THETA = 0.5    # relocation coefficient


# Status + quick link to map
st.caption("Using coordinate from Map page")
coord = st.session_state.get("clicked_coord")

row = st.columns([1, 3])
with row[0]:
    st.page_link(
        "pages/20_Price_Areas_Map_Selector.py",
        label="Pick / change coordinate on the map",
        icon=":material/location_on:"
    )

if coord:
    st.success(f"Coordinate selected: **({coord[0]:.5f}, {coord[1]:.5f})**")
else:
    st.warning("No coordinate selected yet. Please open **Price Areas Map — Choropleth & Click-to-Select** and click the map.")
    st.stop()  # bail until a point is chosen


# Utilities (Tabler functions) 
def compute_Qupot(hourly_wind_speeds: List[float], dt: int = 3600) -> float:
    """Potential wind-driven transport (kg/m): sum(u^3.8 * dt)/233847"""
    return float(sum((float(u) ** 3.8) * dt for u in hourly_wind_speeds) / 233847.0)


def _sector_index(deg: float) -> int:
    """Return 0..15 sector index for 16-bin (22.5°) rose."""
    return int(((deg + 11.25) % 360) // 22.5)


def sector_transport(ws: List[float], wd: List[float], dt: int = 3600) -> List[float]:
    """Cumulative transport per 16 sectors (kg/m)."""
    s = [0.0] * 16
    for u, d in zip(ws, wd):
        idx = _sector_index(float(d))
        s[idx] += (float(u) ** 3.8) * dt / 233847.0
    return s


def tabler_transport(T: float, F: float, theta: float, Swe_mm: float,
                     ws: List[float], dt: int = 3600) -> Dict[str, float | str]:
    """Compute Tabler components for one season."""
    Qupot = compute_Qupot(ws, dt)
    Qspot = 0.5 * T * Swe_mm       # snowfall-limited (kg/m)
    Srwe = theta * Swe_mm          # relocated water equivalent (mm)

    if Qupot > Qspot:
        Qinf = 0.5 * T * Srwe
        control = "Snowfall controlled"
    else:
        Qinf = Qupot
        control = "Wind controlled"

    Qt = Qinf * (1 - (0.14 ** (F / T)))  # mean annual snow transport (kg/m)

    return {
        "Qupot (kg/m)": Qupot,
        "Qspot (kg/m)": Qspot,
        "Srwe (mm)": Srwe,
        "Qinf (kg/m)": Qinf,
        "Qt (kg/m)": Qt,
        "Control": control,
    }


# Data loading
@st.cache_data(ttl=3600, show_spinner=True)
def load_era5_point(lat: float, lon: float, start_date: date, end_date: date) -> pd.DataFrame:
    """
    Pull ERA5 hourly data from Open-Meteo for a single point, UTC.
    """
    df = load_openmeteo_point(
        lat,
        lon,
        start_date,
        end_date,
        location_key=f"snow-drift:{lat:.6f},{lon:.6f}",
    )
    if df.empty:
        detail = df.attrs.get("provenance", {}).get("error", "weather is unavailable")
        raise RuntimeError(detail)
    if not df.attrs.get("coverage_complete", False):
        available_end = df.attrs.get("available_end", "unknown")
        raise RuntimeError(f"weather coverage is incomplete; validated data ends at {available_end}")

    # Season label: Jul–Jun → season = year if month>=7 else year-1
    df["season"] = df["time"].dt.year.where(df["time"].dt.month >= 7, df["time"].dt.year - 1)
    return df


def season_span(start_season: int, end_season: int) -> Tuple[date, date]:
    """
    Convert season range (e.g. 2021..2024) to absolute date range:
      [start=YYYY-07-01, end=(end+1)-07-01), with an exclusive end.
    """
    start = date(start_season, 7, 1)
    end = date(end_season + 1, 7, 1)
    return start, end


# UI controls
with st.expander("Advanced Tabler parameters", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        T = st.number_input("Max transport distance T (m)", min_value=100, max_value=10000,
                            value=DEFAULT_T, step=100)
    with c2:
        F = st.number_input("Fetch distance F (m)", min_value=1000, max_value=200000,
                            value=DEFAULT_F, step=1000)
    with c3:
        theta = st.slider("Relocation coefficient θ", 0.0, 1.0, value=float(DEFAULT_THETA), step=0.05)


# load a wide span first time, then let the user choose seasons to analyze
st.subheader("Select seasons (Jul → Jun)")
available_through = (era5_available_end() - pd.Timedelta(days=1)).date()
latest_complete_season = available_through.year - (1 if available_through.month >= 7 else 2)
min_default, max_default = 2021, latest_complete_season
y1, y2 = st.slider("Season range", min_value=2000, max_value=latest_complete_season,
                   value=(min_default, max_default), step=1)

start_date, end_date = season_span(y1, y2)

with st.spinner("Fetching ERA5 hourly data from Open-Meteo…"):
    try:
        df_all = load_era5_point(lat, lon, start_date, end_date)
    except Exception as e:
        st.error(f"Data download failed: {e}")
        st.stop()

# filter to exactly requested seasons
df = df_all[df_all["season"].between(y1, y2)].copy()
if df.empty:
    st.warning("No hourly data in the selected season range.")
    st.stop()

# quick preview
st.dataframe(df.head(24), use_container_width=True, height=240)


# Calculations
def compute_yearly(df_seasoned: pd.DataFrame, T: float, F: float, theta: float) -> pd.DataFrame:
    records = []
    for s in sorted(df_seasoned["season"].unique()):
        # Jul 1 .. Jun 30 for this season
        start = pd.Timestamp(s, 7, 1, tz="UTC")
        end = pd.Timestamp(s + 1, 6, 30, 23, 59, tz="UTC")
        d = df_seasoned[(df_seasoned["time"] >= start) & (df_seasoned["time"] <= end)].copy()
        if d.empty:
            continue
        # hourly SWE: precip if T < +1°C
        d["Swe_hourly"] = np.where(d["temperature_2m (°C)"] < 1.0, d["precipitation (mm)"], 0.0)
        Swe = float(d["Swe_hourly"].sum())  # mm
        ws = d["wind_speed_10m (m/s)"].astype(float).tolist()
        res = tabler_transport(T, F, theta, Swe, ws)
        res["season"] = f"{s}-{s+1}"
        records.append(res)
    return pd.DataFrame(records)


def average_sectors(df_seasoned: pd.DataFrame) -> List[float]:
    """Average 16-sector transport across all seasons in df."""
    per_season = []
    for s in sorted(df_seasoned["season"].unique()):
        start = pd.Timestamp(s, 7, 1, tz="UTC")
        end = pd.Timestamp(s + 1, 6, 30, 23, 59, tz="UTC")
        d = df_seasoned[(df_seasoned["time"] >= start) & (df_seasoned["time"] <= end)].copy()
        if d.empty:
            continue
        ws = d["wind_speed_10m (m/s)"].astype(float).tolist()
        wd = d["wind_direction_10m (°)"].astype(float).tolist()
        per_season.append(sector_transport(ws, wd))
    if not per_season:
        return [0.0] * 16
    return list(np.mean(np.array(per_season), axis=0))


yearly = compute_yearly(df, float(T), float(F), float(theta))
if yearly.empty:
    st.warning("Could not compute any seasonal results for the selected range.")
    st.stop()

# Show Qt across seasons
yearly_disp = yearly.copy()
yearly_disp["Qt (tonnes/m)"] = yearly_disp["Qt (kg/m)"] / 1000.0
st.subheader("Seasonal Qt (tonnes/m)")
st.dataframe(
    yearly_disp[["season", "Qt (tonnes/m)", "Control"]]
        .assign(**{"Qt (tonnes/m)": yearly_disp["Qt (tonnes/m)"].round(2)}),
    hide_index=True, use_container_width=True
)

fig_qt = px.line(
    yearly_disp, x="season", y="Qt (tonnes/m)", markers=True, title="Qt by season (tonnes/m)"
)
fig_qt.update_layout(xaxis_title="Season (Jul→Jun)", yaxis_title="Qt (tonnes/m)")
st.plotly_chart(fig_qt, use_container_width=True)

overall_avg = float(yearly["Qt (kg/m)"].mean())

# Wind rose
st.subheader("Average wind-transport rose (16 sectors)")
sectors = average_sectors(df)  # kg/m per sector
sectors_tonnes = np.array(sectors) / 1000.0

dir_labels = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
              'S','SSW','SW','WSW','W','WNW','NW','NNW']
theta_deg = np.arange(0, 360, 360 / 16)  # bin centers

fig_rose = go.Figure(
    go.Barpolar(
        r=sectors_tonnes,
        theta=theta_deg,
        width=[360/16]*16,
        marker_line_color="black",
        marker_line_width=1,
        opacity=0.85,
        hovertemplate="%{theta}°<br>%{r:.3f} tonnes/m<extra></extra>",
    )
)
fig_rose.update_layout(
    polar=dict(
        angularaxis=dict(
            direction="clockwise",
            rotation=90,  # 0° at North
            tickmode="array",
            tickvals=theta_deg,
            ticktext=dir_labels,
        )
    ),
    title=f"Average directional transport • Overall Qt ≈ {overall_avg/1000.0:.2f} tonnes/m",
    margin=dict(t=60, r=10, b=10, l=10),
)
st.plotly_chart(fig_rose, use_container_width=True)

with st.expander("Fence height calculator (optional)"):
    fence_type = st.selectbox("Fence type", ["Wyoming", "Slat-and-wire", "Solid"])
    def fence_factor(name: str) -> float:
        name = name.lower()
        if name == "wyoming": return 8.5
        if "slat" in name:    return 7.7
        return 2.9
    factor = fence_factor(fence_type)
    # compute H for each season
    tmp = yearly[["season", "Qt (kg/m)"]].copy()
    tmp["Fence H (m)"] = (tmp["Qt (kg/m)"] / 1000.0 / factor) ** (1 / 2.2)
    st.dataframe(tmp.assign(**{"Fence H (m)": tmp["Fence H (m)"].round(2)}),
                 hide_index=True, use_container_width=True)



# Bonus: Monthly snow drift (Jul -> Jun) and overlay with yearly average 
def _season_month_index(dt: pd.Timestamp) -> int:
    """Map calendar months to 'season months' where Jul=1, ..., Jun=12."""
    return ((dt.month - 7) % 12) + 1  # Jul=1 ... Jun=12

def _compute_Qupot_from_speeds(wind_speeds: pd.Series, dt_sec: int = 3600) -> float:
    if len(wind_speeds) == 0:
        return 0.0
    return float(((wind_speeds.astype(float) ** 3.8) * dt_sec).sum() / 233847.0)

def _compute_Qt_for_slice(df_slice: pd.DataFrame, T: float, F: float, theta: float) -> tuple[float, str]:
    """Compute Qt (kg/m) and control type for a slice (month or season)."""
    if df_slice.empty:
        return 0.0, "n/a"

    # Hourly SWE: precip when temperature < +1 °C
    swe_hourly = np.where(
        df_slice["temperature_2m (°C)"].astype(float) < 1.0,
        df_slice["precipitation (mm)"].astype(float),
        0.0,
    )
    Swe = float(np.nansum(swe_hourly))  # mm

    Qupot = _compute_Qupot_from_speeds(df_slice["wind_speed_10m (m/s)"].astype(float))
    Qspot = 0.5 * T * Swe                # snowfall-limited [kg/m]
    Srwe  = theta * Swe                  # relocated water equivalent [mm]

    if Qupot > Qspot:
        Qinf = 0.5 * T * Srwe
        control = "Snowfall controlled"
    else:
        Qinf = Qupot
        control = "Wind controlled"

    Qt = Qinf * (1 - 0.14 ** (F / T))    # [kg/m]
    return float(Qt), control

def compute_monthly_results(df_all: pd.DataFrame,
                            seasons_to_use: list[int],
                            T: float, F: float, theta: float) -> pd.DataFrame:
    """
    Compute Qt per month (Jul..Jun) for each selected season.
    Returns columns:
      season, season_month (1..12), month_start, Qt_kgm, Qt_tonnes, control
    """
    dfx = df_all.copy()
    dfx["time"] = pd.to_datetime(dfx["time"], utc=True)
    dfx = dfx[dfx["season"].isin(seasons_to_use)].copy()

    out_rows = []
    for s in seasons_to_use:
        season_start = pd.Timestamp(year=s, month=7, day=1, tz="UTC")
        season_end   = pd.Timestamp(year=s+1, month=6, day=30, hour=23, minute=59, second=59, tz="UTC")
        block = dfx[(dfx["time"] >= season_start) & (dfx["time"] <= season_end)].copy()
        if block.empty:
            continue

        block["season_month"] = ((block["time"].dt.month - 7) % 12) + 1  # Jul=1 ... Jun=12
        for m_idx, g in block.groupby("season_month", sort=True):
            qt_kgm, ctrl = _compute_Qt_for_slice(g, T=T, F=F, theta=theta)
            out_rows.append({
                "season": s,
                "season_month": int(m_idx),
                "month_start": g["time"].min().to_period("M").to_timestamp(),
                "Qt_kgm": qt_kgm,
                "Qt_tonnes": qt_kgm / 1000.0,
                "control": ctrl
            })
    return pd.DataFrame(out_rows)

# Use the same seasons you used for the yearly calculation
if "yearly" in locals() and not yearly.empty:
    # yearly["season"] looks like "2019-2020" → take start year
    seasons_used = sorted({int(str(s).split("-")[0]) for s in yearly["season"]})
else:
    seasons_used = sorted(df["season"].unique().tolist())

monthly_df = compute_monthly_results(df, seasons_used, T=float(T), F=float(F), theta=float(theta))


# Monthly vs. Yearly Snow Drift (same figure, twin axes) 
st.subheader("Monthly vs. Yearly Snow Drift (Qt)")

if monthly_df.empty:
    st.info("No monthly results for the selected seasons.")
else:
    # Average monthly Qt across selected seasons (Jul..Jun)
    avg_month = (
        monthly_df.groupby("season_month", as_index=False)["Qt_tonnes"]
        .mean()
        .rename(columns={"Qt_tonnes": "Qt_tonnes_avg"})
    )

    month_labels = ["Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar","Apr","May","Jun"]
    # Keep months ordered Jul→Jun even if some are missing
    avg_month["month"] = pd.Categorical(
        [month_labels[i-1] for i in avg_month["season_month"]],
        categories=month_labels,
        ordered=True,
    )
    avg_month = avg_month.sort_values("month")

    # Yearly average Qt (tonnes/m per season) across the same seasons
    yearly_avg_t = float(yearly["Qt (kg/m)"].mean()) / 1000.0

    fig = go.Figure()

    # Bars: monthly (left axis)
    fig.add_trace(go.Bar(
        x=avg_month["month"],
        y=avg_month["Qt_tonnes_avg"],
        name="Monthly Qt (avg across seasons)",
        hovertemplate="%{y:.2f} t/m",
        marker_line_width=0.5,
    ))

    # Line: yearly (right axis)
    fig.add_trace(go.Scatter(
        x=avg_month["month"],
        y=[yearly_avg_t] * len(avg_month),
        mode="lines+markers",
        name="Yearly Qt (average, per season)",
        hovertemplate="%{y:.2f} t/m",
        yaxis="y2",
        line=dict(dash="dash")
    ))

    fig.update_layout(
        xaxis_title="Seasonal month (Jul → Jun)",
        yaxis=dict(title="Monthly Qt (tonnes/m)", rangemode="tozero"),
        yaxis2=dict(
            title="Yearly Qt (tonnes/m per season)",
            overlaying="y",
            side="right",
            showgrid=False,
            rangemode="tozero",
        ),
        hovermode="x unified",
        margin=dict(t=10, r=10, b=10, l=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Monthly Qt by season (table)"):
        pivot = (
            monthly_df
            .pivot_table(index="season", columns="season_month", values="Qt_tonnes", aggfunc="sum")
            .reindex(columns=range(1, 13))
        )
        pivot.columns = month_labels
        st.dataframe(
            pivot.round(2).reset_index().rename(columns={"season": "Season"}),
            use_container_width=True, hide_index=True
        )
