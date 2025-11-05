
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

st.set_page_config(page_title="IND320 – Part 2 resub", layout="wide")

# ─────────────────────────────────────────────────────────────
# Sidebar navigation (4–5 clickable pages; page 4 = production)
# ─────────────────────────────────────────────────────────────
NAV = ["Home", "Data Table", "Explorer", "Energy production", "About"]
page = st.sidebar.radio("Navigate", NAV, index=0)

# ─────────────────────────────────────────────────────────────
# Loaders (cached) — local CSVs only
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_weather_csv(path: Path) -> pd.DataFrame:
    """Part-1 dataset: data/open-meteo-subset.csv"""
    df = pd.read_csv(path)
    df = df.rename(columns=str.strip)
    rename_map = {
        "temperature_2m": "temperature_2m (°C)",
        "precipitation": "precipitation (mm)",
        "windspeed_10m": "wind_speed_10m (m/s)",
        "windgusts_10m": "wind_gusts_10m (m/s)",
        "winddirection_10m": "wind_direction_10m (°)",
    }
    for k, v in rename_map.items():
        if k in df.columns and v not in df.columns:
            df = df.rename(columns={k: v})
    if "time" not in df.columns:
        raise ValueError("Weather CSV must contain a 'time' column.")
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time").reset_index(drop=True)

@st.cache_data(show_spinner=False)
def load_elhub_csv(path: Path) -> pd.DataFrame:
    """Elhub 2021 production by group (hourly)"""
    df = pd.read_csv(path, parse_dates=["start_time"])
    df = df.rename(columns=str.strip)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True).dt.tz_convert("UTC").dt.tz_localize(None)
    expected = {"price_area", "production_group", "start_time", "quantity_kwh"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"Elhub CSV missing columns: {missing}")
    return df

# Paths
ROOT = Path(__file__).resolve().parent
WEATHER_PATH = ROOT / "data" / "open-meteo-subset.csv"
ELHUB_PATH   = ROOT / "data" / "elhub_prod_by_group_hour_2021.csv"

# Load data
try:
    WEATHER = load_weather_csv(WEATHER_PATH)
except Exception as e:
    st.error(f"Failed to load weather CSV at `{WEATHER_PATH}`:\n\n{e}")
    st.stop()

try:
    ELHUB = load_elhub_csv(ELHUB_PATH)
except Exception as e:
    st.error(f"Failed to load Elhub CSV at `{ELHUB_PATH}`:\n\n{e}")
    st.stop()

# Constants / helpers
WEATHER_VARS = [
    "temperature_2m (°C)",
    "precipitation (mm)",
    "wind_speed_10m (m/s)",
    "wind_gusts_10m (m/s)",
    "wind_direction_10m (°)",
]
WEATHER_UNITS = {
    "temperature_2m (°C)": "°C",
    "precipitation (mm)": "mm",
    "wind_speed_10m (m/s)": "m/s",
    "wind_gusts_10m (m/s)": "m/s",
    "wind_direction_10m (°)": "°",
}

AREAS  = sorted(ELHUB["price_area"].dropna().unique().tolist())
GROUPS = sorted(ELHUB["production_group"].dropna().unique().tolist(), key=str.lower)

GROUP_COLORS = {
    "hydro":  "#4C78A8",
    "other":  "#9E9E9E",
    "solar":  "#F58518",
    "thermal":"#E45756",
    "wind":   "#54A24B",
}
def color_for(g):
    return GROUP_COLORS.get(g, plt.get_cmap("tab10")(hash(g) % 10))

def weather_month_labels(df: pd.DataFrame):
    return (df["time"].dt.to_period("M").sort_values().unique().astype(str).tolist())

def elhub_month_labels(df: pd.DataFrame):
    return (df["start_time"].dt.to_period("M").sort_values().unique().astype(str).tolist())

# ─────────────────────────────────────────────────────────────
# PAGE 1 — Home (weather preview)
# ─────────────────────────────────────────────────────────────
def page_home():
    st.title("Dashboard Basics – Weather Data, Part 1")
    st.caption("Use the sidebar to navigate between pages.")
    st.subheader("Quick preview of data")
    st.dataframe(WEATHER.head(20), use_container_width=True)
    st.sidebar.caption("Data is cached for speed.")

# ─────────────────────────────────────────────────────────────
# PAGE 2 — Data Table (weather) with inline sparklines
# ─────────────────────────────────────────────────────────────
def page_data_table():
    st.title("Data Table")
    st.caption("One row per variable. The mini line chart shows the FIRST calendar month of the series.")
    df = WEATHER.copy()
    first_month_start = df["time"].dt.to_period("M").min().to_timestamp()
    first_month_end   = first_month_start + pd.offsets.MonthEnd(0)
    df_first = df[(df["time"] >= first_month_start) & (df["time"] <= first_month_end)].copy()
    st.write(f"First month: **{first_month_start:%Y-%m}** ({first_month_start:%Y-%m-%d} → {first_month_end:%Y-%m-%d}) • Rows: {len(df_first)}")
    rows = []
    for col in WEATHER_VARS:
        if col not in df.columns:
            continue
        full = pd.to_numeric(df[col], errors="coerce")
        first = pd.to_numeric(df_first[col], errors="coerce")
        rows.append({
            "Variable": col,
            "Unit": WEATHER_UNITS.get(col, ""),
            "Min": round(float(full.min()), 2),
            "Mean": round(float(full.mean()), 2),
            "Max": round(float(full.max()), 2),
            "First month (hourly)": first.tolist(),
        })
    summary = pd.DataFrame(rows, columns=["Variable", "Unit", "Min", "Mean", "Max", "First month (hourly)"])
    st.dataframe(
        summary,
        use_container_width=True,
        column_config={
            "First month (hourly)": st.column_config.LineChartColumn(
                "First month (hourly)", width="medium", y_min=None, y_max=None
            )
        },
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────
# PAGE 3 — Explorer (weather) with month range + all/one variable
# ─────────────────────────────────────────────────────────────
def page_explorer():
    st.title("Explorer")
    st.caption("Select a column (or all) and a month range to plot. Data is read from the local CSV and cached.")
    df = WEATHER.copy()
    months = weather_month_labels(df)
    if not months:
        st.info("No months in dataset."); return
    col_left, col_right = st.columns([2, 2], vertical_alignment="center")
    with col_left:
        choice = st.selectbox("Column to plot", ["All columns"] + [v for v in WEATHER_VARS if v in df.columns], index=0)
    with col_right:
        start_label, end_label = st.select_slider("Select month range", options=months, value=(months[0], months[0]))
    start_ts = pd.Period(start_label, freq="M").to_timestamp()
    end_ts   = pd.Period(end_label,   freq="M").to_timestamp() + pd.offsets.MonthEnd(0)
    d = df[(df["time"] >= start_ts) & (df["time"] <= end_ts)].copy()
    fig, ax = plt.subplots(figsize=(11, 4))
    if choice == "All columns":
        present = [v for v in WEATHER_VARS if v in d.columns]
        for col in present:
            s = pd.to_numeric(d[col], errors="coerce")
            if s.max() > s.min():
                s_norm = (s - s.min()) / (s.max() - s.min())
            else:
                s_norm = s * 0.0
            ax.plot(d["time"], s_norm, lw=1.0, label=col)
        ax.set_ylabel("Normalized scale")
        ax.set_title(f"All variables (normalized 0–1) • {start_label} → {end_label}")
    else:
        s = pd.to_numeric(d[choice], errors="coerce")
        ax.plot(d["time"], s, lw=1.0, label=choice)
        ax.set_ylabel(choice)
        ax.set_title(f"{choice} • {start_label} → {end_label}")
    ax.set_xlabel("Time")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.25)
    st.pyplot(fig, clear_figure=True)

# ─────────────────────────────────────────────────────────────
# PAGE 4 — Energy production (Elhub 2021)
# ─────────────────────────────────────────────────────────────
def page_energy():
    st.title("Elhub – Energy production (Page 4)")
    if st.button("Reset cache"):
        st.cache_data.clear()
        st.success("Cache cleared.")
    colA, colB = st.columns([2, 2])
    with colA:
        areas = sorted(ELHUB["price_area"].unique().tolist())
        area = st.radio("Choose price area", areas, index=areas.index("NO1") if "NO1" in areas else 0, horizontal=True)
    d_area = ELHUB[ELHUB["price_area"] == area].copy()
    if d_area.empty:
        st.info("No data for this area."); return
    groups = sorted(d_area["production_group"].dropna().unique().tolist(), key=str.lower)
    months = elhub_month_labels(d_area)
    left, right = st.columns([7, 5], gap="large")
    with right:
        sel_groups = st.multiselect("Production groups", options=groups, default=groups)
        month = st.selectbox("Month", options=months, index=0)
    if not sel_groups:
        st.info("Select at least one group."); return
    # Annual Pie (left)
    with left:
        d_annual = (
            d_area[d_area["production_group"].isin(sel_groups)]
            .groupby("production_group", as_index=False)["quantity_kwh"]
            .sum()
            .sort_values("quantity_kwh", ascending=False)
        )
        fig_pie, ax_pie = plt.subplots(figsize=(7.5, 7.5))
        colors = [color_for(g) for g in d_annual["production_group"]]
        wedges, texts, autotexts = ax_pie.pie(
            d_annual["quantity_kwh"],
            labels=d_annual["production_group"],
            colors=colors,
            autopct="%1.1f%%",
            startangle=90,
            wedgeprops=dict(edgecolor="white", linewidth=1),
            textprops=dict(color="#222"),
        )
        ax_pie.axis("equal")
        ax_pie.set_title(f"Total Production in 2021 – {area}", fontsize=13, pad=10)
        for t in autotexts:
            t.set_fontsize(10); t.set_weight("bold")
        fig_pie.tight_layout()
        st.pyplot(fig_pie, clear_figure=True)
    # Hourly line (right)
    with right:
        p = pd.Period(month, freq="M")
        m_start = p.to_timestamp()
        m_end   = p.to_timestamp() + pd.offsets.MonthEnd(0)
        # d_area["start_time"] already tz-naive (fixed in loader). Compare safely:
        d_month = d_area[
            (d_area["start_time"] >= m_start) &
            (d_area["start_time"] <= m_end) &
            (d_area["production_group"].isin(sel_groups))
        ].copy()
        st.caption(f"Hourly Production – {area} – {month}")
        if d_month.empty:
            st.info("No data for this month/selection.")
        else:
            pivot = (
                d_month.pivot_table(index="start_time", columns="production_group",
                                    values="quantity_kwh", aggfunc="sum")
                .sort_index().fillna(0.0)
            )
            fig, ax = plt.subplots(figsize=(10.5, 4.2))
            # subtle alternating day background
            dates = pivot.index.normalize().unique()
            for i, dt in enumerate(dates):
                if i % 2 == 1:
                    ax.axvspan(dt, dt + pd.Timedelta(days=1), color="#000", alpha=0.04, linewidth=0)
            for g in pivot.columns:
                ax.plot(pivot.index, pivot[g].values, label=g, linewidth=1.4, color=color_for(g))
            ax.set_ylabel("kWh"); ax.set_xlabel("Time"); ax.grid(True, alpha=0.25)
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=10))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            fig.autofmt_xdate()
            if len(pivot.columns) > 4:
                ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, title="Group")
                fig.tight_layout(rect=[0, 0, 0.86, 1])
            else:
                ax.legend(loc="best", frameon=False); fig.tight_layout()
            st.pyplot(fig, clear_figure=True)

# ─────────────────────────────────────────────────────────────
# PAGE 5 — About
# ─────────────────────────────────────────────────────────────
def page_about():
    st.title("About (Part 2 resubmission)")
    st.markdown(
        "- Pages 1–3 use **Part-1 weather data** (`open-meteo-subset.csv`).\n"
        "- Page 4 is **Energy production** using **Elhub 2021** CSV.\n"
        "- Single sidebar with 4–5 clickable pages (no `pages/` folder), matching the instructor’s requirement.\n"
    )

# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────
if page == "Home":
    page_home()
elif page == "Data Table":
    page_data_table()
elif page == "Explorer":
    page_explorer()
elif page == "Energy production":
    page_energy()
else:
    page_about()