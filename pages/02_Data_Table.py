import re
import pandas as pd
import streamlit as st
from data_loader import load_data

st.title("📊 Data Table")
st.caption("One row per variable. The mini line chart shows the FIRST calendar month of the series.")

# --- load & prep
df = load_data()
if "time" not in df.columns:
    st.error("CSV must contain a 'time' column.")
    st.stop()

df = df.dropna(subset=["time"]).sort_values("time")

# first calendar month
first_period = df["time"].dt.to_period("M").min()
start = first_period.start_time
end = first_period.end_time
mask = (df["time"] >= start) & (df["time"] <= end)
first_month = df.loc[mask].copy().sort_values("time")

if first_month.empty:
    st.warning("No rows found in the first month slice.")
    st.stop()

# numeric columns only (exclude 'time')
num_cols = first_month.select_dtypes(include="number").columns.tolist()

rows = []
for col in num_cols:
    s = pd.to_numeric(first_month[col], errors="coerce")
    unit = ""
    m = re.search(r"\(([^)]+)\)", col)  # pull unit from "name (unit)"
    if m:
        unit = m.group(1)

    rows.append(
        {
            "Variable": col,
            "Unit": unit,
            "Min": float(s.min()),
            "Mean": float(s.mean()),
            "Max": float(s.max()),
            # LineChartColumn expects a list of numbers for each cell:
            "First month": s.dropna().astype(float).tolist(),
        }
    )

table = pd.DataFrame(rows)

st.write(
    f"First month: **{first_period}** "
    f"({start.date()} → {end.date()}) • Rows: {len(first_month)}"
)

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
            "First month (hourly)", help=f"Hourly values during {first_period}.", width="medium"
        ),
    },
)
