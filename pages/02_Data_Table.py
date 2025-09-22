
import re
import pandas as pd
import streamlit as st
from data_loader import load_data

st.title("📊 Data Table")
st.caption("One row per variable. Mini line chart shows the first calendar month of data.")

# --- Load & prep
df = load_data()
if "time" not in df.columns:
    st.error("No 'time' column found in the CSV.")
    st.stop()

df = df.dropna(subset=["time"]).sort_values("time")

# First calendar month boundaries (works across pandas versions)
first_period = df["time"].dt.to_period("M").min()
first_month_start = first_period.start_time
first_month_end = first_period.end_time

mask = (df["time"] >= first_month_start) & (df["time"] <= first_month_end)
first_month = df.loc[mask].copy()

if first_month.empty:
    st.warning("First month slice is empty.")
    st.stop()

num_cols = first_month.select_dtypes(include="number").columns.tolist()

# --- Build one row per variable, with the first month's values as a list
rows = []
for col in num_cols:
    s = pd.to_numeric(first_month[col], errors="coerce")
    unit_match = re.search(r"\(([^)]+)\)", col)
    unit = unit_match.group(1) if unit_match else ""
    rows.append(
        {
            "Variable": col,
            "Unit": unit,
            "Min": float(s.min()),
            "Mean": float(s.mean()),
            "Max": float(s.max()),
            "First month": s.dropna().astype(float).tolist(),  # LineChartColumn expects a list of numbers
        }
    )

table = pd.DataFrame(rows)

# --- Info header
st.write(
    f"First calendar month: **{first_period}** "
    f"({first_month_start.date()} → {first_month_end.date()})"
)

# --- Render table with per-row mini line charts
st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Variable": st.column_config.TextColumn("Variable"),
        "Unit": st.column_config.TextColumn("Unit"),
        "Min": st.column_config.NumberColumn("Min", format="%.2f"),
        "Mean": st.column_config.NumberColumn("Mean", format="%.2f"),
        "Max": st.column_config.NumberColumn("Max", format="%.2f"),
        "First month": st.column_config.LineChartColumn(
            "First month (hourly)",
            help=f"Hourly values during {first_period}.",
            width="medium",
        ),
    },
)
