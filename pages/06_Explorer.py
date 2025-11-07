
# pages/06_Explorer.py
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from app_core.loaders.weather import load_openmeteo_era5

st.title("Explorer")
st.caption("Select a column (or all) and a month range to plot. Data is read from the Open-Meteo API and cached.")

area = st.session_state.get("selected_area", "NO1")
year = st.session_state.get("selected_year", 2021)
df = load_openmeteo_era5(area, year).copy()

df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time")

# Variables
vars_all = [
    "temperature_2m (°C)",
    "precipitation (mm)",
    "wind_speed_10m (m/s)",
    "wind_gusts_10m (m/s)",
    "wind_direction_10m (°)",
]
present = [v for v in vars_all if v in df.columns]
options = ["All columns"] + present

col_left, col_right = st.columns([2, 2], vertical_alignment="center")
with col_left:
    choice = st.selectbox("Column to plot", options, index=0)

# Month range slider (first → last month present)
months = pd.period_range(df["time"].min().to_period("M"), df["time"].max().to_period("M"), freq="M")
labels = [m.strftime("%Y-%m") for m in months]
# Use select_slider to pick start & end month
with col_right:
    start_label, end_label = st.select_slider(
        "Select month range",
        options=labels,
        value=(labels[0], labels[0])  
    )

start_month = pd.Period(start_label, freq="M").to_timestamp()
end_month_last = (pd.Period(end_label, freq="M").to_timestamp() + pd.offsets.MonthEnd(0))
mask = (df["time"] >= start_month) & (df["time"] <= end_month_last)
df_rng = df.loc[mask].copy()

# Plot
fig, ax = plt.subplots(figsize=(11, 4))
if choice == "All columns":
    # Normalize 0–1 per column so shapes are comparable
    for col in present:
        s = pd.to_numeric(df_rng[col], errors="coerce")
        if s.max() > s.min():
            s_norm = (s - s.min()) / (s.max() - s.min())
        else:
            s_norm = s * 0.0
        ax.plot(df_rng["time"], s_norm, lw=1.0, label=col)
    ax.set_ylabel("Normalized scale")
    ax.set_title(f"All variables (normalized 0–1) • {start_label} → {end_label}")
else:
    s = pd.to_numeric(df_rng[choice], errors="coerce")
    ax.plot(df_rng["time"], s, lw=1.0, label=choice)
    ax.set_ylabel(choice)
    ax.set_title(f"{choice} • {start_label} → {end_label}")

ax.set_xlabel("Time")
ax.legend(loc="best", fontsize=9)
ax.grid(True, alpha=0.25)
st.pyplot(fig, clear_figure=True)


