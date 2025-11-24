
# pages/14_Data_Table.py
import pandas as pd
import plotly.express as px
import streamlit as st
from app_core.loaders.weather import load_openmeteo_era5

st.title("Data Table (Weather)")
st.caption("A quick statistical overview + interactive Plotly chart for the selected area & year.")

# global selection (shared across app) 
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
    """
    Return (start_utc, end_utc) for the first calendar month present in df['time'].
    Works even though Period.to_timestamp() is tz-naive.
    """
    p = df["time"].dt.to_period("M").min()             # Period (no tz)
    start = p.to_timestamp(how="start").tz_localize("UTC")
    end = p.to_timestamp(how="end").tz_localize("UTC")
    return start, end

df = get_weather(area, year)

# --- variable meta (display names & units) ---
VARS_UNITS = [
    ("temperature_2m (°C)",    "°C"),
    ("precipitation (mm)",     "mm"),
    ("wind_speed_10m (m/s)",   "m/s"),
    ("wind_gusts_10m (m/s)",   "m/s"),
    ("wind_direction_10m (°)", "°"),
]
VARS_UNITS = [(v, u) for (v, u) in VARS_UNITS if v in df.columns]

# CONTROLS
with st.sidebar:
    st.header("Chart controls")

    sel_vars = st.multiselect(
        "Variables",
        [v for v, _ in VARS_UNITS],
        default=[v for v, _ in VARS_UNITS],
    )

    freq_label = st.selectbox("Resample", ["Hourly", "Daily", "Weekly"], index=0)
    freq_map = {"Hourly": "H", "Daily": "D", "Weekly": "W"}
    resample_rule = freq_map[freq_label]

    mode = st.radio("Range", ["First month", "Custom"], horizontal=True)
    if mode == "Custom":
        start_def = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
        end_def = pd.Timestamp(year=year, month=12, day=31, tz="UTC")
        start_date, end_date = st.date_input(
            "Date range (UTC)",
            (start_def.date(), end_def.date()),
        )
        # Normalize to UTC timestamps (include end day fully)
        start_ts = pd.Timestamp(start_date, tz="UTC")
        end_ts = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    else:
        start_ts, end_ts = first_month_span(df)

# Summary table with sparklines
st.subheader("Summary (whole year) + first-month sparkline")
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

# Interactive Plotly chart 
st.subheader("Interactive chart")

if not sel_vars:
    st.info("Pick at least one variable in the sidebar to draw the chart.")
else:
    filtered = df[(df["time"] >= start_ts) & (df["time"] <= end_ts)].copy()

    long_cols = ["time"] + sel_vars
    melted = filtered[long_cols].melt(id_vars="time", var_name="variable", value_name="value")

    if resample_rule != "H":
        # Use sum for precipitation, mean otherwise (per variable)
        def agg_for(var: str) -> str:
            return "sum" if "precipitation" in var.lower() else "mean"

        melted = (
            melted.set_index("time")
                  .groupby("variable")
                  .resample(resample_rule)["value"]
                  .agg(lambda s: s.sum() if agg_for(s.name) == "sum" else s.mean())
                  .reset_index()
        )

    fig = px.line(
        melted,
        x="time",
        y="value",
        color="variable",
        labels={"time": "Time (UTC)", "value": "Value", "variable": "Variable"},
    )
    fig.update_layout(
        hovermode="x unified",
        xaxis=dict(rangeslider=dict(visible=True)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=10, r=10, b=10, l=10),
    )
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Notes"):
    st.markdown(
        """
- Source: **open-meteo ERA5** loader used in earlier parts.
- Sparkline shows the **first calendar month** available in the series.
- Resampling uses **mean** per variable, except **precipitation = sum**.
- All times shown are **UTC**.
        """
    )


