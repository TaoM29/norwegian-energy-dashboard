
# pages/31_SARIMAX_Forecast.py
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from statsmodels.tsa.statespace.sarimax import SARIMAX

# project loaders
from app_core.loaders.mongo_utils import get_db
from app_core.loaders.weather import load_openmeteo_era5


# Page setup
st.title("Forecasting — SARIMAX (Energy)")

# quick explainer for casual users 
st.markdown(
    """
**What this page does**

- Trains a **SARIMAX** model on the selected energy series (*endogenous*) with optional **weather features** (*exogenous*).  
- You control the **training period**, **frequency** (Hourly/Daily), **model orders** `(p,d,q)` and seasonal `(P,D,Q,s)`, and the **forecast horizon**.
- **Dynamic forecasting:** after the orange “dynamic start” line, in-sample points are predicted using the model’s **previous predictions** (multi-step). Before that, predictions are one-step-ahead using actuals.
- **Plot guide:**  
  - Blue = actuals, Gray = fitted (in-sample), Pink = forecast, Dark band = **95% confidence interval**.  
  - A dotted vertical line marks the **end of training**; everything to the right is the forecast horizon.
- **Aggregation rules:** when using *Daily* frequency, energy → **sum**; weather → **mean** (temperature/wind) and **sum** (precipitation).
- Check the side tab for **Controls**.

*Tip:* Start with small orders and a sensible season length (`s=24` for hourly daily cycle, `s=7` for daily weekly cycle). Then adjust horizon and exogenous variables to see how the forecast and its uncertainty respond.
"""
)



# Global selection from page 02
AREA = st.session_state.get("selected_area", "NO1")
YEAR = int(st.session_state.get("selected_year", 2024))
st.page_link("pages/02_Price_Area_Selector.py", label="Change area / year", icon=":material/settings:")
st.caption(f"Active selection → **Area:** {AREA} • **Year:** {YEAR}")


# Cached DB client
@st.cache_resource
def _db():
    return get_db()

db = _db()


# Helpers / Loaders
def _energy_collections_for_span(kind: str, start: datetime, end: datetime) -> List[Tuple[str, str]]:
    """Return (collection, group_field) across the span (handles 2021 vs 2022–2024 split)."""
    years = range(start.year, end.year + 1)
    out = []
    if kind == "Production":
        for y in years:
            if y <= 2021:
                out.append(("prod_hour", "production_group"))
            else:
                out.append(("elhub_production_mba_hour", "production_group"))
    else:  # Consumption
        for y in years:
            out.append(("elhub_consumption_mba_hour", "consumption_group"))
    # de-dupe preserving order
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq

@st.cache_data(ttl=900, show_spinner=False, max_entries=128)
def load_energy_span_cached(area: str, kind: str, group: str,
                            start_iso: str, end_iso: str) -> pd.DataFrame:
    """Load hourly energy (quantity_kwh) for [start,end] with stable cache keys."""
    start = datetime.fromisoformat(start_iso)
    end   = datetime.fromisoformat(end_iso)
    colls = _energy_collections_for_span(kind, start, end)
    frames = []
    for coll_name, group_field in colls:
        pipe = [
            {"$match": {
                "price_area": area,
                group_field: group,
                "start_time": {"$gte": start, "$lte": end},
            }},
            {"$project": {"_id": 0, "start_time": 1, "quantity_kwh": 1}},
        ]
        rows = list(db[coll_name].aggregate(pipe, allowDiskUse=True))
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=["time", "quantity_kwh"])
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["start_time"], utc=True)
    df = df[["time", "quantity_kwh"]].sort_values("time").reset_index(drop=True)
    return df[(df["time"] >= pd.Timestamp(start, tz="UTC")) & (df["time"] <= pd.Timestamp(end, tz="UTC"))]

@st.cache_data(ttl=1800, show_spinner=False, max_entries=64)
def load_weather_span_cached(area: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    """Load ERA5 hourly weather for [start,end] by stitching per-year files (cached)."""
    start = datetime.fromisoformat(start_iso)
    end   = datetime.fromisoformat(end_iso)
    frames = []
    for y in range(start.year, end.year + 1):
        w = load_openmeteo_era5(area, y).copy()
        w["time"] = pd.to_datetime(w["time"], utc=True)
        frames.append(w)
    if not frames:
        return pd.DataFrame()
    dfw = pd.concat(frames, ignore_index=True)
    dfw = dfw[(dfw["time"] >= pd.Timestamp(start, tz="UTC")) & (dfw["time"] <= pd.Timestamp(end, tz="UTC"))]
    return dfw.sort_values("time").reset_index(drop=True)

# Align energy + weather at requested frequency
def aggregate_freq(df_energy: pd.DataFrame, df_weather: pd.DataFrame, freq: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Align energy and weather at requested frequency.
    freq: "H" or "D"
    Energy is kWh → sum for resampling to daily.
    Weather: temp/wind = mean; precipitation = sum.
    """
    if freq == "H":
        e = df_energy.set_index("time").asfreq("H")
        e["quantity_kwh"] = e["quantity_kwh"].astype(float).fillna(0.0)
        w = df_weather.set_index("time").asfreq("H")
        for col in w.columns:
            if col == "precipitation (mm)":
                w[col] = w[col].astype(float).fillna(0.0)
            else:
                w[col] = w[col].astype(float).interpolate(limit=6)
        return e, w

    # Daily
    e = (df_energy.set_index("time")
         .resample("D")["quantity_kwh"]
         .sum()
         .to_frame())
    agg = {}
    for c in df_weather.columns:
        if c == "time": continue
        agg[c] = "sum" if "precipitation" in c else "mean"
    w = df_weather.set_index("time").resample("D").agg(agg)
    return e, w

# Build future exogenous values
def build_exog_future(exog_train: pd.DataFrame, horizon: int, freq: str, strategy: str) -> pd.DataFrame:
    """
    Create future exogenous values for forecasting.
      - 'last': repeat the last observed row
      - 'hod-mean': hour-of-day mean (hourly) / day-of-week mean (daily)
    """
    if exog_train.empty:
        return exog_train

    last_index = exog_train.index[-1]
    if freq == "H":
        fut_index = pd.date_range(last_index + pd.Timedelta(hours=1), periods=horizon, freq="H", tz="UTC")
    else:
        fut_index = pd.date_range(last_index + pd.Timedelta(days=1), periods=horizon, freq="D", tz="UTC")

    if strategy == "last":
        fut_vals = pd.DataFrame(np.repeat(exog_train.iloc[[-1]].to_numpy(), horizon, axis=0),
                                index=fut_index, columns=exog_train.columns)
    elif strategy == "hod-mean":
        if freq == "H":
            means = exog_train.groupby(exog_train.index.hour).mean(numeric_only=True)
            fut_vals = pd.DataFrame(index=fut_index, columns=exog_train.columns, dtype=float)
            fut_vals.loc[:] = [means.loc[h].values for h in fut_index.hour]
        else:
            means = exog_train.groupby(exog_train.index.dayofweek).mean(numeric_only=True)
            fut_vals = pd.DataFrame(index=fut_index, columns=exog_train.columns, dtype=float)
            fut_vals.loc[:] = [means.loc[d].values for d in fut_index.dayofweek]
    else:
        fut_vals = pd.DataFrame(np.repeat(exog_train.iloc[[-1]].to_numpy(), horizon, axis=0),
                                index=fut_index, columns=exog_train.columns)
    return fut_vals


# UI
with st.sidebar:
    st.header("Controls")

    kind = st.radio("Energy kind", ["Production", "Consumption"], horizontal=False)
    groups = (["hydro", "wind", "solar", "thermal", "nuclear", "other"]
              if kind == "Production"
              else ["household", "cabin", "primary", "secondary", "tertiary"])
    group = st.selectbox("Energy group", groups, index=0)

    freq_label = st.selectbox("Frequency", ["Hourly", "Daily"], index=0)
    FREQ = "H" if freq_label == "Hourly" else "D"

    # Training window
    st.markdown("**Training period**")
    def_year_start = datetime(YEAR, 1, 1)
    def_year_end   = datetime(YEAR, 12, 31, 23, 59, 59)
    train_start, train_end = st.date_input("Start / End (UTC)", (def_year_start.date(), def_year_end.date()))
    TRAIN_START = datetime(train_start.year, train_start.month, train_start.day)
    TRAIN_END   = datetime(train_end.year, train_end.month, train_end.day, 23, 59, 59)

    horizon = st.number_input("Forecast horizon", min_value=1, max_value=2000,
                              value=168 if FREQ == "H" else 30, step=1)

    st.markdown("---")
    st.markdown("**Exogenous weather**")
    WEATHER_CHOICES = [
        "temperature_2m (°C)",
        "precipitation (mm)",
        "wind_speed_10m (m/s)",
        "wind_gusts_10m (m/s)",
        "wind_direction_10m (°)",
    ]
    exog_vars = st.multiselect("Select weather variables", WEATHER_CHOICES, default=[])
    exog_future_strategy = st.selectbox("Future exog strategy", ["last", "hod-mean"], index=0,
                                        help="How to create exogenous values during the forecast horizon.")

    st.markdown("---")
    st.markdown("**SARIMA orders**")
    p = st.number_input("p", 0, 5, 1); d = st.number_input("d", 0, 2, 1); q = st.number_input("q", 0, 5, 1)
    seasonal = st.checkbox("Seasonal order", value=True)
    if seasonal:
        P = st.number_input("P", 0, 5, 1); D = st.number_input("D", 0, 2, 0); Q = st.number_input("Q", 0, 5, 1)
        if FREQ == "H":
            default_s = 24
            s_help = "Seasonal period s (e.g., 24 for daily pattern, 168 for weekly)."
        else:
            default_s = 7
            s_help = "Seasonal period s (e.g., 7 for weekly pattern)."
        s = st.number_input("s (season length)", 2, 24*14, default_s, help=s_help)
    else:
        P = D = Q = 0; s = 0

    st.markdown("---")
    st.markdown("**Dynamic forecasting**")
    dynamic_toggle = st.checkbox("Use dynamic forecasting inside training", value=True,
                                 help="If enabled, one-step-ahead after `dynamic start` becomes multi-step.")
    dyn_pct = st.slider("Dynamic start (as % into training)", 0, 100, 70, step=5)
    st.caption("Tip: if model fails to converge, try smaller orders or disable seasonality.")


# Load & Prepare
with st.status("Loading energy + weather…", expanded=False) as status:
    dfE_hourly = load_energy_span_cached(AREA, kind, group, TRAIN_START.isoformat(), TRAIN_END.isoformat())
    if dfE_hourly.empty:
        status.update(label="No energy rows for the selected period/group.", state="error")
        st.error("No energy rows for the selected period/group.")
        st.stop()

    dfW_hourly = load_weather_span_cached(AREA, TRAIN_START.isoformat(), TRAIN_END.isoformat())
    e, w = aggregate_freq(dfE_hourly, dfW_hourly, FREQ)

    # Build endog/exog
    y = e["quantity_kwh"].astype(float).copy().asfreq(FREQ)
    X = None
    if exog_vars:
        missing = [v for v in exog_vars if v not in w.columns]
        if missing:
            st.warning(f"These weather variables are missing and will be ignored: {missing}")
        use_cols = [v for v in exog_vars if v in w.columns]
        if use_cols:
            X = w[use_cols].astype(float).reindex(y.index).copy()
    if y.dropna().shape[0] < max(40, (int(p)+int(q)+int(P)+int(Q)+1)*5):
        st.warning("Very short training set; consider expanding the training window.")
    status.update(label="Data loaded", state="complete")


# Fit & Forecast
# dynamic start index
if dynamic_toggle:
    dyn_idx = int(len(y) * (dyn_pct/100))
    dyn_idx = min(max(dyn_idx, 0), len(y)-1)
    dyn_start = y.index[dyn_idx]
else:
    dyn_start = 0  # statsmodels: 0/False means no dynamic part

# future exog
X_future = build_exog_future(X, int(horizon), FREQ, exog_future_strategy) if X is not None else None

with st.spinner("Fitting SARIMAX…"):
    try:
        order = (int(p), int(d), int(q))
        seasonal_order = (int(P), int(D), int(Q), int(s)) if seasonal else (0, 0, 0, 0)
        model = SARIMAX(
            endog=y,
            exog=X,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
            freq=FREQ
        )
        res = model.fit(disp=False)
        aic = float(res.aic)
    except Exception as exc:
        st.exception(exc)
        st.stop()

# in-sample predictions (with/without dynamic)
try:
    pred_insample = res.get_prediction(
        start=y.index[0], end=y.index[-1], dynamic=(dyn_start if dynamic_toggle else False), exog=X
    )
    insample_mean = pred_insample.predicted_mean
except Exception:
    insample_mean = None

# out-of-sample forecast
with st.spinner("Forecasting…"):
    try:
        fc = res.get_forecast(steps=int(horizon), exog=X_future)
        fc_mean = fc.predicted_mean
        fc_ci = fc.conf_int(alpha=0.05)  # 95%
    except Exception as exc:
        st.exception(exc)
        st.stop()

# Plot
st.subheader("Forecast")

fig = go.Figure()
# actuals
fig.add_trace(go.Scatter(x=y.index, y=y, mode="lines", name="Actual", line=dict(width=1.5)))
# in-sample fit
if insample_mean is not None:
    fig.add_trace(go.Scatter(x=insample_mean.index, y=insample_mean, mode="lines",
                             name="Fitted (in-sample)", line=dict(width=1)))
# forecast mean
fig.add_trace(go.Scatter(x=fc_mean.index, y=fc_mean, mode="lines", name="Forecast", line=dict(width=2)))
# confidence band
fig.add_trace(go.Scatter(
    x=fc_ci.index.tolist() + fc_ci.index[::-1].tolist(),
    y=fc_ci.iloc[:, 0].tolist() + fc_ci.iloc[:, 1][::-1].tolist(),
    fill="toself",
    fillcolor="rgba(99, 110, 250, 0.15)",
    line=dict(color="rgba(255,255,255,0)"),
    hoverinfo="skip",
    name="95% CI"
))
# vertical line at training end
fig.add_vline(x=y.index[-1], line_width=1, line_dash="dot", line_color="gray")

# dynamic-start marker
if dynamic_toggle:
    xline = pd.to_datetime(dyn_start)
    fig.add_vline(x=xline, line_width=1, line_dash="dash", line_color="orange")
    fig.add_annotation(
        x=xline, y=1, yref="paper",
        text="dynamic start", showarrow=False,
        xanchor="left", yanchor="top",
        font=dict(color="orange")
    )

fig.update_layout(
    margin=dict(t=30, r=10, b=10, l=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    hovermode="x unified",
)
fig.update_yaxes(title_text=f"{'kWh' if FREQ=='H' else 'kWh/day'}")
fig.update_xaxes(title_text="Time (UTC)")
st.plotly_chart(fig, use_container_width=True)

# Details & Notes
with st.expander("Model details"):
    st.markdown(
        f"""
**Endog**: energy ({kind.lower()} · {group}) in **{AREA}**  
**Frequency**: {FREQ} • **Train**: {y.index[0]} → {y.index[-1]}  
**SARIMA**: order={order}, seasonal_order={seasonal_order} • **AIC**: `{aic:,.1f}`  
**Dynamic**: {dynamic_toggle} (start: {dyn_start if dynamic_toggle else '—'})  
**Exogenous**: {', '.join(exog_vars) if exog_vars else 'none'} (future: {exog_future_strategy if exog_vars else '—'})  
**Horizon**: {horizon} steps
        """
    )

with st.expander("Tips"):
    st.markdown(
        """
- If convergence fails, try smaller orders, increase `d`/`D`, or disable seasonality.
- Hourly frequency: start with `s=24` (daily) or `s=168` (weekly).
- Exogenous forecasting needs future values; this page creates them by:
  - **last**: repeating the last observed weather row, or
  - **hod-mean**: using hour-of-day / day-of-week means.
- For sharper evaluation, you can shorten the training window and visually inspect the forecast overlap.
        """
    )