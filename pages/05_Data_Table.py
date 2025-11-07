
# pages/04_Data_Table.py
import streamlit as st
import pandas as pd
from app_core.loaders.weather import load_openmeteo_era5

st.title("Data Table")
st.caption("One row per variable. Mini line chart shows the FIRST calendar month of the series.")

area = st.session_state.get("selected_area", "NO1")
year = st.session_state.get("selected_year", 2021)
df = load_openmeteo_era5(area, year).copy()

# choose variables & units 
vars_units = [
    ("temperature_2m (°C)", "°C"),
    ("precipitation (mm)", "mm"),
    ("wind_speed_10m (m/s)", "m/s"),
    ("wind_gusts_10m (m/s)", "m/s"),
    ("wind_direction_10m (°)", "°"),
]

# first calendar month slice
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time")
first_month_start = df["time"].dt.to_period("M").min().to_timestamp()
first_month_end = (first_month_start + pd.offsets.MonthEnd(0))
df_first = df[(df["time"] >= first_month_start) & (df["time"] <= first_month_end)].copy()

st.write(
    f"First month: **{first_month_start:%Y-%m}** "
    f"({first_month_start:%Y-%m-%d} → {first_month_end:%Y-%m-%d}) • Rows: {len(df_first)}"
)

# build summary rows with sparkline data 
rows = []
for col, unit in vars_units:
    if col not in df.columns:
        continue
    full = pd.to_numeric(df[col], errors="coerce")
    first = pd.to_numeric(df_first[col], errors="coerce")
    rows.append(
        {
            "Variable": col,
            "Unit": unit,
            "Min": round(float(full.min()), 2),
            "Mean": round(float(full.mean()), 2),
            "Max": round(float(full.max()), 2),
            "First month (hourly)": first.tolist(),  # <-- sparkline data
        }
    )

summary = pd.DataFrame(rows, columns=["Variable", "Unit", "Min", "Mean", "Max", "First month (hourly)"])

# render with an inline sparkline column 
st.dataframe(
    summary,
    use_container_width=True,
    column_config={
        "First month (hourly)": st.column_config.LineChartColumn(
            "First month (hourly)",
            width="medium",
            y_min=None,   # let Streamlit auto-scale per-row
            y_max=None,
        )
    },
    hide_index=True,
)


