
# pages/10_Weather_Overview_Stats_and_Sparklines.py
import calendar
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from app_core.loaders.weather import load_openmeteo_era5

st.title("Weather Overview — Stats & Sparklines")
st.caption("Quick statistical overview of ERA5 weather for the selected area & year.")

# Global selection (shared across app)
area = st.session_state.get("selected_area", "NO1")
year = int(st.session_state.get("selected_year", 2024))
st.caption(f"Active selection → **Area:** {area} • **Year:** {year}")
st.page_link("pages/02_Price_Area_Selector.py", label="Change area/year", icon=":material/settings:")

@st.cache_data(ttl=1800, show_spinner=False)
def get_weather(a: str, y: int) -> pd.DataFrame:
    df = load_openmeteo_era5(a, y).copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)

def first_month_span(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start_utc, end_utc) for the first calendar month present in df['time']."""
    p = df["time"].dt.to_period("M").min()
    start = p.to_timestamp(how="start").tz_localize("UTC")
    end = p.to_timestamp(how="end").tz_localize("UTC")
    return start, end

df = get_weather(area, year)

# Variable meta (display names & units)
VARS_UNITS = [
    ("temperature_2m (°C)",    "°C"),
    ("precipitation (mm)",     "mm"),
    ("wind_speed_10m (m/s)",   "m/s"),
    ("wind_gusts_10m (m/s)",   "m/s"),
    ("wind_direction_10m (°)", "°"),
]
VARS_UNITS = [(v, u) for (v, u) in VARS_UNITS if v in df.columns]


# Summary table + first-month sparkline
st.subheader("Summary of whole year + first-month sparkline")

first_start, first_end = first_month_span(df)
df_first = df[(df["time"] >= first_start) & (df["time"] <= first_end)].copy()

rows = []
for col, unit in VARS_UNITS:
    full = pd.to_numeric(df[col], errors="coerce")
    first = pd.to_numeric(df_first[col], errors="coerce")
    rows.append(
        {
            "Variable": col,
            "Unit": unit,
            "Min": round(float(full.min()), 2),
            "Mean": round(float(full.mean()), 2),
            "Max": round(float(full.max()), 2),
            "First month (hourly)": first.tolist(),
        }
    )

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


# Monthly climatology (mean; precipitation = sum)
st.subheader("Monthly climatology by year")

df["month"] = df["time"].dt.month
month_names = [calendar.month_abbr[i] for i in range(13)]

cols = st.columns(2)
col_ix = 0

for col, unit in VARS_UNITS:
    # Skip wind direction for standard bars (circular variable)
    if "direction" in col.lower():
        continue

    agg = "sum" if "precipitation" in col.lower() else "mean"
    s = df.groupby("month")[col].agg(agg).reindex(range(1, 13))
    disp = pd.DataFrame({"Month": [month_names[i] for i in s.index], "Value": s.values})

    fig = px.bar(
        disp,
        x="Month",
        y="Value",
        title=f"{col} — {'sum' if agg=='sum' else 'mean'} by month",
        labels={"Value": f"{col}"},
    )
    fig.update_layout(margin=dict(t=50, r=10, b=10, l=10))

    with cols[col_ix % 2]:
        st.plotly_chart(fig, use_container_width=True)
    col_ix += 1


# Wind direction: annual wind rose (proper circular summary)
if "wind_direction_10m (°)" in df.columns:
    st.subheader("Wind direction distribution (wind rose, year)")

    dir_deg = pd.to_numeric(df["wind_direction_10m (°)"], errors="coerce").dropna().to_numpy()
    if dir_deg.size > 0:
        # 16 sectors (22.5° each), labels N, NNE, ..., NNW
        labels = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                  'S','SSW','SW','WSW','W','WNW','NW','NNW']
        bins = np.arange(0, 361, 22.5)  # 0..360 inclusive
        # Place 360 exactly into the last bin like 0°
        dir_deg = np.where(dir_deg == 360.0, 0.0, dir_deg)
        counts, _ = np.histogram(dir_deg, bins=bins)

        rose_df = pd.DataFrame({"Sector": labels, "Frequency": counts})
        fig_rose = px.bar_polar(
            rose_df, r="Frequency", theta="Sector",
            title="Wind direction (frequency by sector)",
        )
        fig_rose.update_polars(
            angularaxis_direction="clockwise",
            angularaxis_rotation=90  # put 'N' at the top
        )
        fig_rose.update_layout(margin=dict(t=50, r=10, b=10, l=10))
        st.plotly_chart(fig_rose, use_container_width=True)
    else:
        st.info("No valid wind direction values to plot.")


# Notes
with st.expander("Notes"):
    st.markdown(
        """
- **Sparkline** shows the first calendar month present in the data (hourly).
- **Monthly climatology:** mean for most variables; **precipitation = sum**.
- **Wind direction** is **circular**; we summarize it with a **wind rose** (frequency by sector).
- All times are **UTC**.
        """
    )


