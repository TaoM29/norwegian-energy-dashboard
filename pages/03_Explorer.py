
import re
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from data_loader import load_data

st.title("📈 Explorer")
st.caption("Select a column (or all) and a month range to plot. Data is read from the local CSV and cached.")

# --- load & prep
df = load_data()
if "time" not in df.columns:
    st.error("CSV must contain a 'time' column.")
    st.stop()

df = df.dropna(subset=["time"]).sort_values("time")
df["month"] = df["time"].dt.to_period("M")

# numeric columns for plotting
num_cols = df.select_dtypes(include="number").columns.tolist()

# Build month options
months = sorted(df["month"].unique())
if not months:
    st.warning("No months found in data.")
    st.stop()

# --- controls
col1, col2 = st.columns([1, 2])

with col1:
    column_choice = st.selectbox(
        "Column to plot",
        options=["All columns"] + num_cols,
        index=0,
        help="Choose one numeric column, or plot all together.",
    )

with col2:
    start_m, end_m = st.select_slider(
        "Select month range",
        options=months,
        value=(months[0], months[0]),  # default to FIRST month as required
        help="Drag to choose a subset of months. Defaults to the first month.",
        format_func=lambda p: str(p),
    )

# --- filter data by month range
mask = (df["month"] >= start_m) & (df["month"] <= end_m)
dff = df.loc[mask].copy().set_index("time")

if dff.empty:
    st.warning("No data in the selected month range.")
    st.stop()

# --- plotting
fig, ax = plt.subplots(figsize=(11, 4))

def _extract_unit(colname: str) -> str:
    m = re.search(r"\(([^)]+)\)", colname)
    return m.group(1) if m else ""

if column_choice == "All columns":
    # normalize each series to 0–1 so different scales can share one axis
    norm = (dff[num_cols] - dff[num_cols].min()) / (dff[num_cols].max() - dff[num_cols].min())
    norm.plot(ax=ax, linewidth=0.9)
    ax.set_title(f"All variables (normalized 0–1) • {start_m} → {end_m}")
    ax.set_xlabel("Time")
    ax.set_ylabel("Normalized scale")
    ax.grid(True, linewidth=0.3)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0.)
else:
    unit = _extract_unit(column_choice)
    dff[column_choice].plot(ax=ax, linewidth=1.2)
    ax.set_title(f"{column_choice} • {start_m} → {end_m}")
    ax.set_xlabel("Time")
    ax.set_ylabel(f"{unit or column_choice}")
    ax.grid(True, linewidth=0.3)

st.pyplot(fig)
