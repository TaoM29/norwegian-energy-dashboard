from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from statsmodels.tsa.statespace.sarimax import SARIMAX

from app_core.loaders.mongo_utils import available_years_from_coverage, get_energy_status
from app_core.loaders.weather import load_openmeteo_era5
from app_core.loaders.elhub_span import load_energy_span_df
from app_core.loaders.weather_span import load_weather_span_df
from app_core.analysis.sarimax_utils import (
    aggregate_freq,
    build_exog_future,
    rolling_origin_backtest_sarimax,
)

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
- **MASE** (Mean Absolute Scaled Error) — scaled by seasonal error in each training fold
"""
)

AREA = st.session_state.get("selected_area", "NO1")
st.page_link("pages/02_Price_Area_Selector.py", label="Change area / year", icon=":material/settings:")
STATUS = get_energy_status()
WINDOW = STATUS.get("common_complete_window")
available_years = available_years_from_coverage(STATUS["coverage"], area=AREA)
if not available_years:
    st.error(f"No validated energy coverage is available for {AREA}.")
    st.stop()
YEAR = int(st.session_state.get("selected_year", available_years[-1]))
YEAR = YEAR if YEAR in available_years else available_years[-1]
st.caption(f"Active selection → **Area:** {AREA} • **Year:** {YEAR} · **{STATUS['source']}**")


@st.cache_data(ttl=900, show_spinner=False, max_entries=128)
def load_energy_span_cached(area: str, kind: str, group: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return load_energy_span_df(db=None, area=area, kind=kind, group=group, start=start, end=end)


@st.cache_data(ttl=1800, show_spinner=False, max_entries=64)
def load_weather_span_cached(area: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return load_weather_span_df(load_openmeteo_era5=load_openmeteo_era5, area=area, start=start, end=end)


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
    return rolling_origin_backtest_sarimax(
        y_values=y_values,
        X_values=X_values,
        freq=freq,
        horizon=horizon,
        step_size=step_size,
        folds=folds,
        m_seasonal=m_seasonal,
        order=order,
        seasonal_order=seasonal_order,
        eval_no_exog=eval_no_exog,
    )


with st.sidebar:
    st.header("Controls")

    kind = st.radio("Energy kind", ["Production", "Consumption"], horizontal=False)
    groups = sorted({
        row["group"] for row in STATUS["coverage"]
        if row["area"] == AREA and row["kind"] == kind.lower()
        and row["group"] not in {"*", "industry", "private", "business"}
        and pd.Timestamp(row["start"]) < pd.Timestamp(f"{YEAR + 1}-01-01", tz="UTC")
        and pd.Timestamp(row["end"]) > pd.Timestamp(f"{YEAR}-01-01", tz="UTC")
    })
    group = st.selectbox("Energy group", groups, index=0)
    group_coverage = [
        row for row in STATUS["coverage"]
        if row["area"] == AREA and row["kind"] == kind.lower() and row["group"] == group
    ]
    group_start = max(
        pd.Timestamp(f"{YEAR}-01-01", tz="UTC"),
        min(pd.Timestamp(row["start"]) for row in group_coverage),
    )
    group_end = min(
        pd.Timestamp(f"{YEAR + 1}-01-01", tz="UTC"),
        max(pd.Timestamp(row["end"]) for row in group_coverage),
    )

    freq_label = st.selectbox("Frequency", ["Hourly", "Daily"], index=0)
    FREQ = "H" if freq_label == "Hourly" else "D"

    PANDAS_FREQ = "h" if FREQ == "H" else FREQ

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

    training_start_bound = group_start
    training_end_bound = group_end
    if exog_vars:
        weather_probe = load_weather_span_cached(
            AREA, group_start.isoformat(), group_end.isoformat(),
        )
        probe_metadata = weather_probe.attrs.get("provenance", {})
        if weather_probe.empty or not probe_metadata.get("available_end"):
            st.error(
                "Selected weather regressors are unavailable for this energy period. "
                "Remove them or choose another year."
            )
            st.stop()
        training_start_bound = max(group_start, pd.Timestamp(probe_metadata["available_start"]))
        training_end_bound = min(group_end, pd.Timestamp(probe_metadata["available_end"]))
        if training_start_bound >= training_end_bound:
            st.error("Energy and weather have no common observed interval for the selected year.")
            st.stop()
        st.caption(
            f"Actual common energy/weather coverage ends "
            f"{(training_end_bound - pd.Timedelta(hours=1)):%Y-%m-%d %H:%M UTC}."
        )

    st.markdown("**Training period**")
    def_year_start = training_start_bound.date()
    group_last = training_end_bound - pd.Timedelta(hours=1)
    def_year_end = group_last.date()
    train_start, train_end = st.date_input(
        "Start / End (UTC, inclusive dates)",
        (def_year_start, def_year_end),
        min_value=training_start_bound.date(), max_value=group_last.date(),
    )
    TRAIN_START = datetime(train_start.year, train_start.month, train_start.day, tzinfo=timezone.utc)
    TRAIN_END = datetime(train_end.year, train_end.month, train_end.day, tzinfo=timezone.utc) + timedelta(days=1)
    TRAIN_END = min(TRAIN_END, training_end_bound.to_pydatetime())

    horizon = st.number_input("Forecast horizon", min_value=1, max_value=2000,
                              value=168 if FREQ == "H" else 30, step=1)

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


with st.status("Loading energy + weather…", expanded=False) as status:
    dfE_hourly = load_energy_span_cached(AREA, kind, group, TRAIN_START.isoformat(), TRAIN_END.isoformat())
    if dfE_hourly.empty:
        status.update(label="No energy rows for the selected period/group.", state="error")
        st.error("No energy rows for the selected period/group.")
        st.stop()

    dfW_hourly = load_weather_span_cached(AREA, TRAIN_START.isoformat(), TRAIN_END.isoformat())
    weather_provenance = dfW_hourly.attrs.get("provenance", {})
    weather_cache = weather_provenance.get("cache_status", "unavailable")
    weather_retrieved_at = weather_provenance.get("retrieved_at") or max(
        (
            item.get("retrieved_at")
            for item in weather_provenance.get("annual_provenance", [])
            if item.get("retrieved_at")
        ),
        default="",
    )
    weather_start = (
        pd.Timestamp(weather_provenance["available_start"])
        if weather_provenance.get("available_start") else None
    )
    weather_end = (
        pd.Timestamp(weather_provenance["available_end"])
        if weather_provenance.get("available_end") else None
    )
    actual_common_end = min(pd.Timestamp(TRAIN_END), weather_end) if weather_end is not None else None

    if exog_vars and (
        dfW_hourly.empty
        or weather_cache == "unavailable"
        or not weather_provenance.get("coverage_complete", False)
        or weather_start is None
        or weather_start > pd.Timestamp(TRAIN_START)
        or actual_common_end is None
        or actual_common_end < pd.Timestamp(TRAIN_END)
    ):
        status.update(label="Selected weather regressors are unavailable for the full interval.", state="error")
        available_text = (
            f"{weather_start:%Y-%m-%d %H:%M} → {(weather_end - pd.Timedelta(hours=1)):%Y-%m-%d %H:%M UTC}"
            if weather_start is not None and weather_end is not None else "unavailable"
        )
        st.warning(
            "SARIMAX was not fitted because selected weather regressors do not cover the full "
            f"training interval. Actual weather coverage: {available_text}. "
            "Choose an end date within that coverage or remove the weather regressors."
        )
        st.stop()

    try:
        e, w = aggregate_freq(dfE_hourly, dfW_hourly, PANDAS_FREQ)
    except ValueError as exc:
        status.update(label="The selected interval is incomplete.", state="error")
        st.warning(str(exc))
        st.stop()

    y = e["quantity_kwh"].astype(float).copy().asfreq(PANDAS_FREQ)
    if y.isna().any():
        status.update(label="Energy data contains gaps.", state="error")
        st.warning("The selected interval contains missing energy periods. Choose a complete interval before fitting.")
        st.stop()

    X = None
    if exog_vars:
        missing = [v for v in exog_vars if v not in w.columns]
        if missing:
            status.update(label="Selected weather regressors are missing.", state="error")
            st.warning(f"SARIMAX was not fitted because these selected weather variables are missing: {missing}")
            st.stop()
        X = w[exog_vars].astype(float).reindex(y.index).copy()
        if X.isna().any().any():
            status.update(label="Weather regressors contain gaps.", state="error")
            st.warning("Selected weather regressors contain missing periods. Choose another interval or remove them.")
            st.stop()

    status.update(label="Data loaded", state="complete")

if not dfW_hourly.empty and weather_start is not None and weather_end is not None:
    weather_model = (
        "ERA5-Seamless" if weather_provenance.get("model") == "era5_seamless"
        else weather_provenance.get("model", "ERA5-Seamless")
    )
    weather_retrieved = (
        f" · retrieved **{pd.Timestamp(weather_retrieved_at):%Y-%m-%d %H:%M UTC}**"
        if weather_retrieved_at else ""
    )
    st.caption(
        f"Weather: **{weather_provenance.get('source', 'Open-Meteo')} / "
        f"{weather_model}** · actual coverage loaded: "
        f"**{weather_start:%Y-%m-%d %H:%M} → "
        f"{(weather_end - pd.Timedelta(hours=1)):%Y-%m-%d %H:%M UTC}**{weather_retrieved}"
    )
    if weather_cache == "stale_snapshot":
        st.warning("The source refresh failed, so this run uses the last-known-good weather snapshot.")


if dynamic_toggle:
    dyn_idx = int(len(y) * (dyn_pct / 100))
    dyn_idx = min(max(dyn_idx, 0), len(y) - 1)
    dyn_start = y.index[dyn_idx]
else:
    dyn_start = 0

order = (int(p), int(d), int(q))
seasonal_order = (int(P), int(D), int(Q), int(s)) if seasonal else (0, 0, 0, 0)

X_future = build_exog_future(
    X,
    int(horizon),
    PANDAS_FREQ,
    exog_future_strategy,
) if X is not None else None


with st.spinner("Fitting SARIMAX…"):
    try:
        model = SARIMAX(
            endog=y,
            exog=X,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
            freq=PANDAS_FREQ,
        )
        res = model.fit(disp=False)
        aic = float(res.aic)
    except Exception as exc:
        st.exception(exc)
        st.stop()

try:
    pred_insample = res.get_prediction(
        start=y.index[0], end=y.index[-1], dynamic=(dyn_start if dynamic_toggle else False), exog=X
    )
    insample_mean = pred_insample.predicted_mean
except Exception:
    insample_mean = None

with st.spinner("Forecasting…"):
    try:
        fc = res.get_forecast(steps=int(horizon), exog=X_future)
        fc_mean = fc.predicted_mean
        fc_ci = fc.conf_int(alpha=0.05)
    except Exception as exc:
        st.exception(exc)
        st.stop()


st.subheader("Forecast")

fig = go.Figure()
fig.add_trace(go.Scatter(x=y.index, y=y, mode="lines", name="Actual", line=dict(width=1.5)))

if insample_mean is not None:
    fig.add_trace(go.Scatter(x=insample_mean.index, y=insample_mean, mode="lines", name="Fitted (in-sample)", line=dict(width=1)))

fig.add_trace(go.Scatter(x=fc_mean.index, y=fc_mean, mode="lines", name="Forecast", line=dict(width=2)))

fig.add_trace(go.Scatter(
    x=fc_ci.index.tolist() + fc_ci.index[::-1].tolist(),
    y=fc_ci.iloc[:, 0].tolist() + fc_ci.iloc[:, 1][::-1].tolist(),
    fill="toself",
    fillcolor="rgba(99, 110, 250, 0.15)",
    line=dict(color="rgba(255,255,255,0)"),
    hoverinfo="skip",
    name="95% CI",
))

fig.add_vline(x=y.index[-1], line_width=1, line_dash="dot", line_color="gray")

if dynamic_toggle:
    xline = pd.to_datetime(dyn_start)
    fig.add_vline(x=xline, line_width=1, line_dash="dash", line_color="orange")
    fig.add_annotation(x=xline, y=1, yref="paper", text="dynamic start", showarrow=False, xanchor="left", yanchor="top", font=dict(color="orange"))

fig.update_layout(
    margin=dict(t=30, r=10, b=10, l=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    hovermode="x unified",
)
fig.update_yaxes(title_text=f"{'kWh' if FREQ == 'H' else 'kWh/day'}")
fig.update_xaxes(title_text="Time (UTC)")
st.plotly_chart(fig, use_container_width=True)


st.subheader("Backtesting & baselines")
st.caption("Retained retrospective analysis: exogenous backtests use realized test-period weather, an upper-bound experiment. Publication lags are not reconstructed here. Use the Forecasts workspace for availability-aware evaluation and stored results.")

if do_backtest:
    with st.spinner("Running rolling backtest (this may take a bit)…"):
        summary_bt, artifacts = rolling_backtest_cached(
            y_values=y,
            X_values=X,
            freq=PANDAS_FREQ,
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
            "MASE uses the training fold's seasonal error as its scale. "
            "Use the held-out MAE and RMSE rows to compare models with the displayed seasonal-naive baseline."
        )
else:
    st.info("Enable **Run rolling backtest** in the sidebar to compare SARIMAX vs the seasonal-naive baseline.")


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
