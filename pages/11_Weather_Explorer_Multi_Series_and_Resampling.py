
# pages/11_Weather_Explorer_Multi_Series_and_Resampling.py
import pandas as pd
import plotly.express as px
import streamlit as st

from app_core.loaders.weather import load_openmeteo_era5
from app_core.loaders.mongo_utils import available_years_from_coverage, get_energy_status

st.title("Weather Explorer — Multi-Series & Resampling")
st.caption("Pick variables, resample/smooth, and a month range. Data comes from Open-Meteo and is cached.")

# global selection (from 02_Price_Area_Selector.py) 
area = st.session_state.get("selected_area", "NO1")
energy_status = get_energy_status()
available_years = available_years_from_coverage(energy_status["coverage"], area=area)
if not available_years:
    st.error("No validated energy coverage is available for the shared year selection.")
    st.stop()
year = int(st.session_state.get("selected_year", available_years[-1]))
year = year if year in available_years else available_years[-1]
st.caption(f"Active selection → **Area:** {area} • **Year:** {year}")
st.page_link("pages/02_Price_Area_Selector.py", label="Change area/year", icon=":material/settings:")

# load & cache
@st.cache_data(ttl=1800, show_spinner=False)
def get_weather(a: str, y: int) -> pd.DataFrame:
    df = load_openmeteo_era5(a, y).copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)

df = get_weather(area, year)
if df.empty:
    st.info(f"No ERA5-Seamless observations are available for {area} in {year}.")
    st.stop()
provenance = df.attrs.get("provenance", {})
cache_status = provenance.get("cache_status", "unknown")
model_label = "ERA5-Seamless" if provenance.get("model") == "era5_seamless" else provenance.get("model", "ERA5-Seamless")
retrieved_text = (
    f" · retrieved **{pd.Timestamp(provenance['retrieved_at']):%Y-%m-%d %H:%M UTC}**"
    if provenance.get("retrieved_at") else ""
)
st.caption(
    f"Weather source: **{provenance.get('source', 'Open-Meteo')} / {model_label}** · "
    f"actual coverage through **{(pd.Timestamp(provenance['available_end']) - pd.Timedelta(hours=1)) if provenance.get('available_end') else df['time'].max():%Y-%m-%d %H:%M UTC}**"
    f"{retrieved_text}"
)
if cache_status == "stale_snapshot":
    st.warning("The source refresh failed, so this page is using the last-known-good weather snapshot.")

# available variables (keep only those present)
VARS_ALL = [
    "temperature_2m (°C)",
    "precipitation (mm)",
    "wind_speed_10m (m/s)",
    "wind_gusts_10m (m/s)",
    "wind_direction_10m (°)",
]
VARS_PRESENT = [v for v in VARS_ALL if v in df.columns]

# controls
left, right = st.columns([2, 2])
with left:
    sel_vars = st.multiselect(
        "Variables to plot",
        options=VARS_PRESENT,
        default=VARS_PRESENT,  
    )
with right:
    # Month range (first → last month present)
    months = pd.period_range(df["time"].min().to_period("M"),
                             df["time"].max().to_period("M"),
                             freq="M")
    month_labels = [m.strftime("%Y-%m") for m in months]
    start_lbl, end_lbl = st.select_slider(
        "Select month range",
        options=month_labels,
        value=(month_labels[0], month_labels[-1]),
    )

# extra options
c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.1, 2])
with c1:
    normalize = st.toggle("Normalize 0–1", value=True, help="Scale each series to its own min/max within the chosen date range.")
with c2:
    smooth_h = st.number_input("Rolling mean (h)", min_value=0, max_value=240, value=24, step=1,
                               help="0 disables smoothing.")
with c3:
    resample_choice = st.selectbox("Resample", ["Hourly", "Daily", "Weekly"], index=0)
    rule = {"Hourly": "h", "Daily": "D", "Weekly": "W"}[resample_choice]
with c4:
    opacity = st.slider("Line opacity", 0.1, 1.0, 0.9, 0.05)

if not sel_vars:
    st.info("Pick at least one variable to draw the chart.")
    st.stop()

# filter to selected months
start_ts = pd.Period(start_lbl, freq="M").start_time.tz_localize("UTC")
end_ts = (pd.Period(end_lbl, freq="M") + 1).start_time.tz_localize("UTC")
mask = (df["time"] >= start_ts) & (df["time"] < end_ts)
df_rng = df.loc[mask, ["time", *sel_vars]].copy()

if df_rng.empty:
    st.warning("No rows in the selected range.")
    st.stop()

# reshape long for plotly 
long = df_rng.melt(id_vars="time", var_name="variable", value_name="value")

# resample (per variable) 
if rule != "h":
    resampled = []
    for variable, values in long.groupby("variable"):
        hourly = values.set_index("time")["value"]
        aggregated = (hourly.resample(rule).sum(min_count=1)
                      if "precipitation" in variable.lower()
                      else hourly.resample(rule).mean())
        resampled.append(aggregated.rename("value").reset_index().assign(variable=variable))
    long = pd.concat(resampled, ignore_index=True)

# smoothing (rolling mean in hours) 
if smooth_h and smooth_h > 0:
    long = (
        long.set_index("time")
            .groupby("variable")["value"]
            .rolling(f"{smooth_h}h").mean()
            .reset_index()
    )

# normalization 0–1 (per variable over the chosen window) 
if normalize:
    mins = long.groupby("variable")["value"].transform("min")
    maxs = long.groupby("variable")["value"].transform("max")
    span = (maxs - mins).replace(0, 1)  # avoid div by zero
    long["value"] = (long["value"] - mins) / span

# plot 
title_suffix = f"{start_lbl} → {end_lbl}"
y_label = "Normalized (0–1)" if normalize else "Value"
fig = px.line(
    long,
    x="time",
    y="value",
    color="variable",
    labels={"time": "Time (UTC)", "value": y_label, "variable": "Variable"},
    title=f"{'All variables' if len(sel_vars)>1 else sel_vars[0]} • {title_suffix}",
    render_mode="webgl",  # faster for lots of points
)
fig.update_traces(opacity=opacity)
fig.update_layout(
    hovermode="x unified",
    xaxis=dict(rangeslider=dict(visible=True)),
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.15,       # put legend under the x-axis
        xanchor="left",
        x=0,
    ),
    margin=dict(t=40, r=10, b=70, l=10),  # extra bottom space for legend
)

st.plotly_chart(fig, use_container_width=True)

with st.expander("Notes"):
    st.markdown(
        """
- **Normalize 0–1** scales each series using min/max within the chosen date range.
- **Rolling mean** smooths short-term variation (set to 0 to disable).
- **Resample** uses *sum* for precipitation and *mean* for other variables.
- Try clicking legend items to hide/show series; double-click isolates one series.
        """
    )
