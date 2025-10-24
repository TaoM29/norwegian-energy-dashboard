import re
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from data_loader import load_data


st.set_page_config(page_title="Dashboard Basics – Weather Data", layout="wide")


# ---------- Sidebar "pages" ----------
with st.sidebar:
    st.header("Navigate")
    page = st.radio("Go to", ["Home", "Data Table", "Explorer", "About"], index=0, label_visibility="collapsed")
    st.markdown("---")
    st.caption("Data is cached for speed.")



# ---------- Load data once ----------
df = load_data()  # cached
if "time" in df.columns:
    df = df.dropna(subset=["time"]).sort_values("time")
else:
    st.error("CSV must contain a 'time' column.")
    st.stop()


# Helpers
def first_month_slice(_df: pd.DataFrame) -> tuple[pd.DataFrame, str, pd.Timestamp, pd.Timestamp]:
    period = _df["time"].dt.to_period("M").min()
    start, end = period.start_time, period.end_time
    out = _df.loc[(_df["time"] >= start) & (_df["time"] <= end)].copy().sort_values("time")
    return out, str(period), start, end

def extract_unit(colname: str) -> str:
    m = re.search(r"\(([^)]+)\)", colname)
    return m.group(1) if m else ""



# ---------- Page: Home ----------
if page == "Home":
    st.title("📊 IND320 — Project Work, Part 1")
    st.caption("Use the sidebar to navigate between pages.")
    st.subheader("Quick preview of data")
    st.dataframe(df.head(), use_container_width=True)



# ---------- Page: Data Table ----------
elif page == "Data Table":
    st.title("📊 Data Table")
    st.caption("One row per variable. The mini line chart shows the FIRST calendar month of the series.")

    first_month, period_str, start, end = first_month_slice(df)
    if first_month.empty:
        st.warning("First month slice is empty.")
        st.stop()

    num_cols = first_month.select_dtypes(include="number").columns.tolist()

    rows = []
    for col in num_cols:
        s = pd.to_numeric(first_month[col], errors="coerce")
        rows.append(
            {
                "Variable": col,
                "Unit": extract_unit(col),
                "Min": float(s.min()),
                "Mean": float(s.mean()),
                "Max": float(s.max()),
                "First month": s.dropna().astype(float).tolist(),  # LineChartColumn expects list[float]
            }
        )
    table = pd.DataFrame(rows)

    st.write(f"First month: **{period_str}** ({start.date()} → {end.date()}) • Rows: {len(first_month)}")

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
                "First month (hourly)", help=f"Hourly values during {period_str}.", width="medium"
            ),
        },
    )



# ---------- Page: Explorer ----------
elif page == "Explorer":
    st.title("📈 Explorer")
    st.caption("Select a column (or all) and a month range to plot. Data is read from the local CSV and cached.")

    df_m = df.copy()
    df_m["month"] = df_m["time"].dt.to_period("M")
    months = sorted(df_m["month"].unique())
    num_cols = df_m.select_dtypes(include="number").columns.tolist()

    col1, col2 = st.columns([1, 2])
    with col1:
        choice = st.selectbox("Column to plot", ["All columns"] + num_cols, index=0)
    with col2:
        start_m, end_m = st.select_slider(
            "Select month range",
            options=months,
            value=(months[0], months[0]),  # defaults to first month (as required)
            format_func=lambda p: str(p),
            help="Drag to choose a subset of months. Defaults to the first month.",
        )

    mask = (df_m["month"] >= start_m) & (df_m["month"] <= end_m)
    dff = df_m.loc[mask].copy().set_index("time")
    if dff.empty:
        st.warning("No data in the selected month range.")
        st.stop()

    fig, ax = plt.subplots(figsize=(11, 4))
    if choice == "All columns":
        
        # normalize to share one y-axis
        norm = (dff[num_cols] - dff[num_cols].min()) / (dff[num_cols].max() - dff[num_cols].min())
        norm.plot(ax=ax, linewidth=0.9)
        ax.set_title(f"All variables (normalized 0–1) • {start_m} → {end_m}")
        ax.set_xlabel("Time")
        ax.set_ylabel("Normalized scale")
        ax.grid(True, linewidth=0.3)
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))
    else:
        unit = extract_unit(choice)
        dff[choice].plot(ax=ax, linewidth=1.2)
        ax.set_title(f"{choice} • {start_m} → {end_m}")
        ax.set_xlabel("Time")
        ax.set_ylabel(unit or choice)
        ax.grid(True, linewidth=0.3)
    st.pyplot(fig)



# ---------- Page: About ----------
else:
    st.title("ℹ️ About")
    st.markdown(
        """
**Course:** IND320 – Project Work, Part 1  
**Data:** `data/open-meteo-subset.csv`  
**App:** https://ind320-project-work-nonewthing.streamlit.app  
**Repo:** https://github.com/TaoM29/IND320-project-work

This app includes four pages with sidebar navigation:
- Home (data preview)
- Data Table (row-wise LineChartColumn for first month)
- Explorer (plot with column select + month range slider)
- About (project meta)

Data loading is cached via `@st.cache_data` in `data_loader.py`.
"""
    )





