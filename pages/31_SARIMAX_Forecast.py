# pages/31_SARIMAX_Forecast.py
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from statsmodels.tsa.statespace.sarimax import SARIMAX

# project loaders
from app_core.loaders.mongo_utils import get_db
from app_core.loaders.weather import load_openmeteo_era5



st.title("Forecasting — SARIMAX (Energy)")

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

**Backtesting & baselines (model evaluation)**

- Runs a **rolling-origin backtest**: fit the model multiple times on historical data and forecast a fixed horizon each time.  
- Compares SARIMAX against a strong baseline: **seasonal naive**  
  - Hourly default: `m = 168` → “same hour last week”  
  - Daily default: `m = 7` → “same day last week”
- Reports average performance across folds using:
  - **MAE** (Mean Absolute Error) — lower is better  
  - **RMSE** (Root Mean Squared Error) — penalizes large errors  
  - **MASE** (Mean Absolute Scaled Error) — **< 1 means better than the seasonal-naive baseline**

- Check the side tab for **Controls** (including backtest horizon, step size, and number of folds).
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
    out: List[Tuple[str, str]] = []
    if kind == "Production":
        for y in years:
            if y <= 2021:
                out.append(("prod_hour", "production_group"))
            else:
                out.append(("elhub_production_mba_hour", "production_group"))
    else:  # Consumption
        for _y in years:
            out.append(("elhub_consumption_mba_hour", "consumption_group"))

    # de-dupe preserving order
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq



@st.cache_data(ttl=900, show_spinner=False, max_entries=128)
def load_energy_span_cached(area: str, kind: str, group: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    """Load hourly energy (quantity_kwh) for [start,end] with stable cache keys."""
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    colls = _energy_collections_for_span(kind, start, end)

    frames: List[pd.DataFrame] = []
    for coll_name, group_field in colls:
        pipe = [
            {
                "$match": {
                    "price_area": area,
                    group_field: group,
                    "start_time": {"$gte": start, "$lte": end},
                }
            },
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

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return df[(df["time"] >= start_ts) & (df["time"] <= end_ts)]



@st.cache_data(ttl=1800, show_spinner=False, max_entries=64)
def load_weather_span_cached(area: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    """Load ERA5 hourly weather for [start,end] by stitching per-year files (cached)."""
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)

    frames: List[pd.DataFrame] = []
    for y in range(start.year, end.year + 1):
        w = load_openmeteo_era5(area, y).copy()
        w["time"] = pd.to_datetime(w["time"], utc=True)
        frames.append(w)

    if not frames:
        return pd.DataFrame()

    dfw = pd.concat(frames, ignore_index=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    dfw = dfw[(dfw["time"] >= start_ts) & (dfw["time"] <= end_ts)]
    return dfw.sort_values("time").reset_index(drop=True)



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
    e = df_energy.set_index("time").resample("D")["quantity_kwh"].sum().to_frame()

    agg: Dict[str, str] = {}
    for c in df_weather.columns:
        if c == "time":
            continue
        agg[c] = "sum" if "precipitation" in c else "mean"
    w = df_weather.set_index("time").resample("D").agg(agg)

    return e, w



def build_exog_future(exog_train: pd.DataFrame, horizon: int, freq: str, strategy: str) -> pd.DataFrame:
    """
    Create future exogenous values for forecasting.
      - 'last': repeat the last observed row
      - 'hod-mean': hour-of-day mean (hourly) / day-of-week mean (daily)
    """
    if exog_train is None or exog_train.empty:
        return exog_train

    last_index = exog_train.index[-1]
    if freq == "H":
        fut_index = pd.date_range(last_index + pd.Timedelta(hours=1), periods=horizon, freq="H", tz="UTC")
    else:
        fut_index = pd.date_range(last_index + pd.Timedelta(days=1), periods=horizon, freq="D", tz="UTC")

    if strategy == "last":
        fut_vals = pd.DataFrame(
            np.repeat(exog_train.iloc[[-1]].to_numpy(), horizon, axis=0),
            index=fut_index,
            columns=exog_train.columns,
        )
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
        fut_vals = pd.DataFrame(
            np.repeat(exog_train.iloc[[-1]].to_numpy(), horizon, axis=0),
            index=fut_index,
            columns=exog_train.columns,
        )

    # final cleanup
    fut_vals = fut_vals.astype(float)
    fut_vals = fut_vals.interpolate(limit=6).bfill().ffill()
    return fut_vals




# Backtesting helpers
def _mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    a = (y_true - y_pred).abs().dropna()
    return float(a.mean()) if len(a) else float("nan")


def _rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    a = (y_true - y_pred).dropna()
    if not len(a):
        return float("nan")
    return float(np.sqrt(np.mean(a.to_numpy() ** 2)))


def _mase(y_true: pd.Series, y_pred: pd.Series, y_train: pd.Series, m: int) -> float:
    y_train = y_train.dropna()
    if len(y_train) < 3:
        return float("nan")

    # scale = mean abs seasonal naive error on training
    if len(y_train) <= m:
        scale = float(y_train.diff().abs().dropna().mean())  # fallback
    else:
        scale = float(np.mean(np.abs(y_train.iloc[m:].to_numpy() - y_train.iloc[:-m].to_numpy())))

    if not np.isfinite(scale) or scale == 0:
        return float("nan")

    return _mae(y_true, y_pred) / scale



def _seasonal_naive_forecast(y_train: pd.Series, horizon: int, m: int, freq: str) -> pd.Series:
    y_train = y_train.dropna()
    if len(y_train) == 0:
        return pd.Series(dtype=float)

    m_eff = max(1, min(int(m), len(y_train)))
    last_season = y_train.iloc[-m_eff:].to_numpy()
    reps = int(math.ceil(horizon / m_eff))
    vals = np.tile(last_season, reps)[:horizon]

    idx = pd.date_range(y_train.index[-1] + pd.tseries.frequencies.to_offset(freq), periods=horizon, freq=freq, tz="UTC")
    return pd.Series(vals, index=idx)



@st.cache_data(ttl=900, show_spinner=False, max_entries=32)
def rolling_backtest_cached(
    y_values: pd.Series,
    X_values: Optional[pd.DataFrame],
    freq: str,
    horizon: int,
    step_size: int,
    folds: int,
    m_seasonal: int,
    order: tuple[int, int, int],
    seasonal_order: tuple[int, int, int, int],
    eval_no_exog: bool,
) -> tuple[pd.DataFrame, dict]:
    """
    Rolling-origin backtest inside the available y_values span.

    Returns:
      - summary table: mean/std by model for MAE/RMSE/MASE
      - artifacts for plotting last fold: y_test, baseline, sarimax_best, sarimax_no_exog, sarimax_exog
    """
    y = y_values.dropna().copy()
    if len(y) < (horizon + max(60, 2 * max(1, m_seasonal))):
        return pd.DataFrame(), {}

    X = None
    if X_values is not None and not X_values.empty:
        X = X_values.reindex(y.index).copy().astype(float)
        X = X.interpolate(limit=6).bfill().ffill()

    min_train = max(60, 2 * max(1, m_seasonal), 5 * (order[0] + order[2] + seasonal_order[0] + seasonal_order[2] + 1))
    last_cutoff_pos = len(y) - horizon - 1
    cut_positions = [last_cutoff_pos - step_size * k for k in range(int(folds))][::-1]
    cut_positions = [p for p in cut_positions if p >= min_train]
    if not cut_positions:
        return pd.DataFrame(), {}

    def fit_forecast(y_train: pd.Series, X_train: Optional[pd.DataFrame], X_test: Optional[pd.DataFrame]) -> Optional[pd.Series]:
        try:
            model = SARIMAX(
                endog=y_train,
                exog=X_train,
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
                freq=freq,
            )
            res = model.fit(disp=False)
            fc = res.get_forecast(steps=int(horizon), exog=X_test)
            return fc.predicted_mean
        except Exception:
            return None

    rows = []
    artifacts: dict = {}

    for pos in cut_positions:
        y_train = y.iloc[: pos + 1]
        y_test = y.iloc[pos + 1 : pos + 1 + horizon]

        # baseline
        y_base = _seasonal_naive_forecast(y_train, horizon=int(horizon), m=int(m_seasonal), freq=freq)
        rows.append(
            {
                "model": "Seasonal naive",
                "fold": int(pos),
                "MAE": _mae(y_test, y_base),
                "RMSE": _rmse(y_test, y_base),
                "MASE": _mase(y_test, y_base, y_train, m=int(m_seasonal)),
            }
        )

        # SARIMAX no exog
        y_hat_no = None
        if eval_no_exog or X is None:
            y_hat_no = fit_forecast(y_train, None, None)
            if y_hat_no is not None:
                rows.append(
                    {
                        "model": "SARIMAX (no exog)",
                        "fold": int(pos),
                        "MAE": _mae(y_test, y_hat_no),
                        "RMSE": _rmse(y_test, y_hat_no),
                        "MASE": _mase(y_test, y_hat_no, y_train, m=int(m_seasonal)),
                    }
                )

        # SARIMAX with exog
        y_hat_ex = None
        if X is not None:
            X_train = X.iloc[: pos + 1]
            X_test = X.iloc[pos + 1 : pos + 1 + horizon]
            y_hat_ex = fit_forecast(y_train, X_train, X_test)
            if y_hat_ex is not None:
                rows.append(
                    {
                        "model": "SARIMAX (+exog)",
                        "fold": int(pos),
                        "MAE": _mae(y_test, y_hat_ex),
                        "RMSE": _rmse(y_test, y_hat_ex),
                        "MASE": _mase(y_test, y_hat_ex, y_train, m=int(m_seasonal)),
                    }
                )

        # keep last fold artifacts for plotting
        if pos == cut_positions[-1]:
            artifacts = {
                "y_test": y_test,
                "baseline": y_base,
                "sarimax_no_exog": y_hat_no,
                "sarimax_exog": y_hat_ex,
            }
            artifacts["sarimax_best"] = y_hat_ex if y_hat_ex is not None else y_hat_no

    df_folds = pd.DataFrame(rows)

    summary = (
        df_folds.groupby("model")[["MAE", "RMSE", "MASE"]]
        .agg(["mean", "std"])
        .reset_index()
    )

    # Flatten columns for display
    cols = []
    for c in summary.columns:
        if isinstance(c, tuple):
            if c[1] == "":
                cols.append(c[0])
            else:
                cols.append(f"{c[0]}_{c[1]}")
        else:
            cols.append(str(c))
    summary.columns = cols

    # sort models in a nice order
    order_models = ["Seasonal naive", "SARIMAX (no exog)", "SARIMAX (+exog)"]
    summary["__ord"] = summary["model"].apply(lambda x: order_models.index(x) if x in order_models else 999)
    summary = summary.sort_values("__ord").drop(columns="__ord").reset_index(drop=True)

    return summary, artifacts




# UI (Sidebar)
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
    def_year_end = datetime(YEAR, 12, 31, 23, 59, 59)
    train_start, train_end = st.date_input("Start / End (UTC)", (def_year_start.date(), def_year_end.date()))
    TRAIN_START = datetime(train_start.year, train_start.month, train_start.day)
    TRAIN_END = datetime(train_end.year, train_end.month, train_end.day, 23, 59, 59)

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
    exog_future_strategy = st.selectbox(
        "Future exog strategy",
        ["last", "hod-mean"],
        index=0,
        help="How to create exogenous values during the forecast horizon.",
    )

    st.markdown("---")
    st.markdown("**SARIMA orders**")
    p = st.number_input("p", 0, 5, 1)
    d = st.number_input("d", 0, 2, 1)
    q = st.number_input("q", 0, 5, 1)

    seasonal = st.checkbox("Seasonal order", value=True)
    if seasonal:
        P = st.number_input("P", 0, 5, 1)
        D = st.number_input("D", 0, 2, 0)
        Q = st.number_input("Q", 0, 5, 1)

        if FREQ == "H":
            default_s = 24
            s_help = "Seasonal period s (e.g., 24 for daily pattern, 168 for weekly)."
            s_max = 24 * 14
        else:
            default_s = 7
            s_help = "Seasonal period s (e.g., 7 for weekly pattern)."
            s_max = 60

        s = st.number_input("s (season length)", 2, int(s_max), int(default_s), help=s_help)
    else:
        P = D = Q = 0
        s = 0

    st.markdown("---")
    st.markdown("**Dynamic forecasting**")
    dynamic_toggle = st.checkbox(
        "Use dynamic forecasting inside training",
        value=True,
        help="If enabled, one-step-ahead after `dynamic start` becomes multi-step.",
    )
    dyn_pct = st.slider("Dynamic start (as % into training)", 0, 100, 70, step=5)

    st.markdown("---")
    st.markdown("**Backtesting (rolling origin)**")
    do_backtest = st.checkbox("Run rolling backtest", value=True)

    m_seasonal = st.number_input(
        "Seasonal naive lag (m)",
        min_value=1,
        max_value=int(24 * 14) if FREQ == "H" else 60,
        value=168 if FREQ == "H" else 7,
        help="Baseline uses ŷ(t)=y(t−m). Hourly: 168 = weekly seasonality. Daily: 7 = weekly.",
    )
    bt_horizon = st.number_input(
        "Backtest horizon (steps)",
        min_value=1,
        max_value=2000,
        value=168 if FREQ == "H" else 7,
        help="How far ahead to forecast in each fold.",
    )
    step_size = st.number_input(
        "Backtest step (steps between cutoffs)",
        min_value=1,
        max_value=2000,
        value=24 if FREQ == "H" else 1,
        help="How far the train end moves forward each fold.",
    )
    folds = st.number_input(
        "Folds",
        min_value=1,
        max_value=25,
        value=5,
        help="How many rolling-origin splits to evaluate.",
    )
    eval_no_exog = st.checkbox(
        "Also evaluate SARIMAX without exogenous vars",
        value=True if exog_vars else False,
        help="Lets you compare: baseline vs SARIMAX w/ and w/o exogenous weather.",
    )

    st.caption("Tip: if the model fails to converge, try smaller orders or disable seasonality.")



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
            X = X.interpolate(limit=6).bfill().ffill()

    if y.dropna().shape[0] < max(40, (int(p) + int(q) + int(P) + int(Q) + 1) * 5):
        st.warning("Very short training set; consider expanding the training window.")

    status.update(label="Data loaded", state="complete")



# Fit & Forecast (single fit on full training span)
# dynamic start index
if dynamic_toggle:
    dyn_idx = int(len(y) * (dyn_pct / 100))
    dyn_idx = min(max(dyn_idx, 0), len(y) - 1)
    dyn_start = y.index[dyn_idx]
else:
    dyn_start = 0  # statsmodels: 0/False means no dynamic part

order = (int(p), int(d), int(q))
seasonal_order = (int(P), int(D), int(Q), int(s)) if seasonal else (0, 0, 0, 0)

# future exog
X_future = build_exog_future(X, int(horizon), FREQ, exog_future_strategy) if X is not None else None

with st.spinner("Fitting SARIMAX…"):
    try:
        model = SARIMAX(
            endog=y,
            exog=X,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
            freq=FREQ,
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




# Plot (main)
st.subheader("Forecast")

fig = go.Figure()
fig.add_trace(go.Scatter(x=y.index, y=y, mode="lines", name="Actual", line=dict(width=1.5)))

if insample_mean is not None:
    fig.add_trace(
        go.Scatter(
            x=insample_mean.index,
            y=insample_mean,
            mode="lines",
            name="Fitted (in-sample)",
            line=dict(width=1),
        )
    )

fig.add_trace(go.Scatter(x=fc_mean.index, y=fc_mean, mode="lines", name="Forecast", line=dict(width=2)))

# confidence band
fig.add_trace(
    go.Scatter(
        x=fc_ci.index.tolist() + fc_ci.index[::-1].tolist(),
        y=fc_ci.iloc[:, 0].tolist() + fc_ci.iloc[:, 1][::-1].tolist(),
        fill="toself",
        fillcolor="rgba(99, 110, 250, 0.15)",
        line=dict(color="rgba(255,255,255,0)"),
        hoverinfo="skip",
        name="95% CI",
    )
)

# vertical line at training end
fig.add_vline(x=y.index[-1], line_width=1, line_dash="dot", line_color="gray")

# dynamic-start marker
if dynamic_toggle:
    xline = pd.to_datetime(dyn_start)
    fig.add_vline(x=xline, line_width=1, line_dash="dash", line_color="orange")
    fig.add_annotation(
        x=xline,
        y=1,
        yref="paper",
        text="dynamic start",
        showarrow=False,
        xanchor="left",
        yanchor="top",
        font=dict(color="orange"),
    )

fig.update_layout(
    margin=dict(t=30, r=10, b=10, l=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    hovermode="x unified",
)
fig.update_yaxes(title_text=f"{'kWh' if FREQ == 'H' else 'kWh/day'}")
fig.update_xaxes(title_text="Time (UTC)")
st.plotly_chart(fig, use_container_width=True)




# Backtesting & baselines
st.subheader("Backtesting & baselines")

if do_backtest:
    with st.spinner("Running rolling backtest (this may take a bit)…"):
        summary_bt, artifacts = rolling_backtest_cached(
            y_values=y,
            X_values=X,
            freq=FREQ,
            horizon=int(bt_horizon),
            step_size=int(step_size),
            folds=int(folds),
            m_seasonal=int(m_seasonal),
            order=order,
            seasonal_order=seasonal_order,
            eval_no_exog=bool(eval_no_exog),
        )

    if summary_bt.empty:
        st.info("Not enough data points for the chosen backtest settings. Try smaller horizon/folds/lag or a larger date span.")
    else:
        st.markdown("**Average metrics across folds (mean ± std)**")
        st.dataframe(summary_bt, use_container_width=True, hide_index=True)

        y_test = artifacts.get("y_test")
        y_base = artifacts.get("baseline")
        y_best = artifacts.get("sarimax_best")

        if isinstance(y_test, pd.Series) and isinstance(y_base, pd.Series):
            st.markdown("**Last fold preview**")

            fig_bt = go.Figure()
            fig_bt.add_trace(go.Scatter(x=y_test.index, y=y_test, mode="lines", name="Actual (test)", line=dict(width=2)))
            fig_bt.add_trace(go.Scatter(x=y_base.index, y=y_base, mode="lines", name="Seasonal naive", line=dict(width=1)))

            if isinstance(y_best, pd.Series):
                name = "SARIMAX (+exog)" if artifacts.get("sarimax_exog") is not None else "SARIMAX (no exog)"
                fig_bt.add_trace(go.Scatter(x=y_best.index, y=y_best, mode="lines", name=name, line=dict(width=2, dash="dash")))

            fig_bt.update_layout(hovermode="x unified", margin=dict(t=30, r=10, b=10, l=10))
            fig_bt.update_xaxes(title_text="Time (UTC)")
            fig_bt.update_yaxes(title_text=f"{'kWh' if FREQ == 'H' else 'kWh/day'}")
            st.plotly_chart(fig_bt, use_container_width=True)

        st.caption(
            "MASE < 1 means the model beats the seasonal-naive baseline on average. "
            "Increase the date span to get more valid folds."
        )
else:
    st.info("Enable **Run rolling backtest** in the sidebar to compare SARIMAX vs the seasonal-naive baseline.")



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
- Backtesting uses rolling-origin splits *inside the selected span*; expand the training window to run more folds.
        """
    )