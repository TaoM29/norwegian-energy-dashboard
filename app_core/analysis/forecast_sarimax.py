"""Explicit SARIMAX experiments on published observations, outside page execution."""
from __future__ import annotations

import warnings
from typing import Callable

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from app_core.analysis.sarimax_utils import aggregate_freq
from app_core.ingestion.models import BASE_GROUPS

WEATHER = ["temperature_2m (°C)", "precipitation (mm)", "wind_speed_10m (m/s)", "wind_gusts_10m (m/s)", "wind_direction_10m (°)"]


def validate_sarimax_config(config: dict) -> dict:
    defaults = dict(area="NO1", kind="consumption", group="household", start="2025-01-01", end="2025-04-01", frequency="h", horizon=24, order=[1, 1, 1], seasonalOrder=[0, 0, 0, 0], weatherVariables=[], futureWeather="last", dynamic=True, dynamicStart=0.7, backtest=True, baselineLag=168, backtestHorizon=24, step=24, folds=3, evalNoExog=True, energyLagHours=48, weatherLagHours=120)
    unknown = set(config) - set(defaults)
    if unknown:
        raise ValueError(f"Unknown SARIMAX settings: {', '.join(sorted(unknown))}")
    c = {**defaults, **config}
    if c["frequency"] == "D":
        if "baselineLag" not in config:
            c["baselineLag"] = 7
        if "step" not in config:
            c["step"] = 1
        if "backtestHorizon" not in config:
            c["backtestHorizon"] = 7
    if c["area"] not in [f"NO{i}" for i in range(1, 6)] or c["kind"] not in BASE_GROUPS or c["group"] not in (set(BASE_GROUPS[c["kind"]]) | ({"nuclear"} if c["kind"] == "production" else set())):
        raise ValueError("Choose a valid area and disjoint energy group.")
    if c["frequency"] not in ("h", "D") or c["futureWeather"] not in ("last", "hod-mean"):
        raise ValueError("Choose hourly/daily frequency and last/hod-mean weather.")
    try:
        start, end = pd.Timestamp(c["start"]), pd.Timestamp(c["end"])
        if start.tzinfo or end.tzinfo or start != start.normalize() or end != end.normalize() or not 2 <= (end-start).days <= 366:
            raise ValueError()
    except Exception as exc:
        raise ValueError("Training dates must span 2–366 complete UTC days, with exclusive end.") from exc
    c["start"], c["end"] = str(start.date()), str(end.date())
    for key, low, high in [("horizon", 1, 168 if c["frequency"] == "h" else 60), ("baselineLag", 1, 336 if c["frequency"] == "h" else 60), ("backtestHorizon", 1, 168 if c["frequency"] == "h" else 60), ("step", 1, 168), ("folds", 1, 5), ("energyLagHours", 0, 168), ("weatherLagHours", 0, 336)]:
        if isinstance(c[key], bool) or not isinstance(c[key], int) or not low <= c[key] <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}.")
    if c["frequency"] == "D" and (c["energyLagHours"] % 24 or c["weatherLagHours"] % 24):
        raise ValueError("Daily experiments require publication lags in complete days.")
    for key, bounds in [("order", [3, 2, 3]), ("seasonalOrder", [1, 1, 1, 168 if c["frequency"] == "h" else 60])]:
        values = c[key]
        if not isinstance(values, (list, tuple)) or len(values) != len(bounds) or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= cap for v, cap in zip(values, bounds)):
            raise ValueError(f"Invalid {key}.")
        c[key] = list(values)
    p, d, q = c["order"]
    P, D, Q, s = c["seasonalOrder"]
    if (P or D or Q) and s < 2:
        raise ValueError("Enabled seasonality requires a period of at least two.")
    if not (P or D or Q):
        c["seasonalOrder"] = [0, 0, 0, 0]
    if max(p + P*s, q + Q*s + 1) + d + D*s > 64:
        raise ValueError("This seasonal order exceeds the 64-state experiment limit; reduce the period or seasonal orders.")
    if not isinstance(c["weatherVariables"], list) or any(v not in WEATHER for v in c["weatherVariables"]):
        raise ValueError("Unknown weather regressor.")
    c["weatherVariables"] = list(dict.fromkeys(c["weatherVariables"]))
    if isinstance(c["dynamicStart"], bool) or not isinstance(c["dynamicStart"], (int, float)) or not 0 <= c["dynamicStart"] <= 1:
        raise ValueError("Dynamic start must be a fraction from zero to one.")
    for key in ("dynamic", "backtest", "evalNoExog"):
        if not isinstance(c[key], bool):
            raise ValueError(f"{key} must be true or false.")
    return c


def _project_weather(history: pd.DataFrame, index: pd.DatetimeIndex, strategy: str, frequency: str) -> pd.DataFrame:
    """Fill only from observations available before this origin; never future truth."""
    history = history.sort_index().ffill().dropna()
    if history.empty:
        raise ValueError("No complete weather history is available at the assumed issue time.")
    result = history.reindex(index).copy()
    if strategy == "hod-mean":
        groups = history.index.hour if frequency == "h" else history.index.dayofweek
        means = history.groupby(groups).mean()
        fallback = history.iloc[-1]
        for timestamp in index:
            key = timestamp.hour if frequency == "h" else timestamp.dayofweek
            if timestamp > history.index[-1]:
                result.loc[timestamp] = means.loc[key] if key in means.index else fallback
    return result.ffill().dropna()


def _baseline(y: pd.Series, index: pd.DatetimeIndex, lag: int, frequency: str) -> pd.Series:
    offset = pd.tseries.frequencies.to_offset(frequency)
    output = {}
    for timestamp in index:
        reference = timestamp - lag * offset
        while reference > y.index[-1]:
            reference -= lag * offset
        output[timestamp] = y.get(reference, np.nan)
    return pd.Series(output, dtype=float)


def _fit(y: pd.Series, x: pd.DataFrame | None, issue: pd.Timestamp, horizon: int, c: dict) -> dict:
    frequency = c["frequency"]
    offset = pd.tseries.frequencies.to_offset(frequency)
    target = pd.date_range(issue, periods=horizon, freq=frequency)
    future = pd.date_range(y.index[-1] + offset, target[-1], freq=frequency)
    x_train = x_future = None
    if x is not None:
        # A source interval is available only after its end plus the declared lag.
        available = x.loc[x.index + offset + pd.Timedelta(hours=c["weatherLagHours"]) <= issue]
        combined = _project_weather(available, y.index.union(future), c["futureWeather"], frequency)
        x_train = combined.reindex(y.index)
        x_future = combined.reindex(future)
        if x_train.isna().any().any() or x_future.isna().any().any():
            raise ValueError("Weather regressors have missing leading history; choose a later training start.")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = SARIMAX(y, exog=x_train, order=tuple(c["order"]), seasonal_order=tuple(c["seasonalOrder"]), enforce_stationarity=False, enforce_invertibility=False, freq=frequency).fit(disp=False, maxiter=100)
    prediction = result.get_forecast(steps=len(future), exog=x_future)
    interval = prediction.conf_int(alpha=.05)
    frame = pd.DataFrame({"prediction": prediction.predicted_mean, "lower": interval.iloc[:, 0], "upper": interval.iloc[:, 1]}).reindex(target)
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("The fitted model produced non-finite forecasts.")
    frame["baseline"] = _baseline(y, target, c["baselineLag"], frequency)
    fitted = pd.DataFrame({"actual": y, "fitted": result.fittedvalues})
    if c["dynamic"]:
        dynamic_position = min(len(y)-1, int(len(y) * c["dynamicStart"]))
        fitted["dynamic"] = result.get_prediction(start=0, end=len(y)-1, dynamic=dynamic_position).predicted_mean
    return {"forecast": frame, "training": fitted, "aic": float(result.aic), "converged": bool(result.mle_retvals.get("converged", True)), "warnings": list(dict.fromkeys(str(w.message) for w in caught))}


def _rows(frame: pd.DataFrame) -> list:
    import json
    return json.loads(frame.rename_axis("time").reset_index().to_json(orient="records", date_format="iso", double_precision=15))


def run_sarimax(config: dict, progress: Callable | None = None, cancelled: Callable | None = None) -> dict:
    from backend.data import energy_frame, weather_frame
    c = validate_sarimax_config(config)
    def report(fraction: float, message: str):
        if cancelled and cancelled():
            raise InterruptedError("Experiment cancelled")
        if progress:
            progress(fraction, message)
    report(.02, "Reading published source observations")
    energy = energy_frame(c["area"], c["start"], c["end"], c["kind"], [c["group"]])
    weather = weather_frame(c["area"], c["start"], c["end"]) if c["weatherVariables"] else pd.DataFrame()
    e = energy.rename(columns={"timestamp": "time", "value": "quantity_kwh"})[["time", "quantity_kwh"]]
    w = weather[["time", *c["weatherVariables"]]] if not weather.empty else weather
    e, w = aggregate_freq(e, w, c["frequency"])
    grid = pd.date_range(c["start"], c["end"], freq=c["frequency"], inclusive="left", tz="UTC")
    y = e["quantity_kwh"].reindex(grid)
    if len(y) < max(30, 2*c["baselineLag"]) or y.notna().sum() < 30 or not np.isfinite(y.iloc[-1]):
        raise ValueError("Choose a training interval with an observed final value and at least two baseline seasons / 30 observed steps.")
    # Missing targets remain on their actual timestamps. State-space fitting handles them.
    x = w.reindex(grid) if not w.empty else None
    issue = pd.Timestamp(c["end"], tz="UTC") + pd.Timedelta(hours=c["energyLagHours"])
    report(.1, "Fitting SARIMAX and its conditional prediction interval")
    fitted = _fit(y, x, issue, c["horizon"], c)
    predictions, failures = [], []
    offset = pd.tseries.frequencies.to_offset(c["frequency"])
    gap = c["energyLagHours"] // (1 if c["frequency"] == "h" else 24)
    variants = [("SARIMAX", x)]
    if x is not None and c["evalNoExog"]:
        variants.append(("SARIMAX (no exog)", None))
    if c["backtest"]:
        last_cut = len(y)-gap-c["backtestHorizon"]
        for fold, cut in enumerate(range(last_cut-(c["folds"]-1)*c["step"], last_cut+1, c["step"])):
            report(.2+.7*fold/c["folds"], f"Evaluating fold {fold+1} of {c['folds']}")
            if cut < max(30, 2*c["baselineLag"]):
                failures.append({"fold": fold, "reason": "Insufficient training history", "model": "all"})
                continue
            train = y.iloc[:cut]
            fold_issue = train.index[-1]+offset+pd.Timedelta(hours=c["energyLagHours"])
            target = pd.date_range(fold_issue, periods=c["backtestHorizon"], freq=c["frequency"])
            actual = y.reindex(target)
            baseline = _baseline(train, target, c["baselineLag"], c["frequency"])
            if actual.isna().any() or baseline.isna().any():
                failures.append({"fold": fold, "origin": fold_issue.isoformat(), "model": "all", "reason": "Missing target or seasonal baseline; matched fold excluded"})
                continue
            scale = (train-train.shift(c["baselineLag"])).abs().mean()
            fold_outputs = [("Seasonal naive", baseline)]
            for name, exog in variants:
                try:
                    output = _fit(train, exog, fold_issue, c["backtestHorizon"], c)
                    if not output["converged"]:
                        raise ValueError("Optimizer did not converge")
                    fold_outputs.append((name, output["forecast"]["prediction"]))
                except Exception as exc:
                    failures.append({"fold": fold, "origin": fold_issue.isoformat(), "model": name, "reason": str(exc)})
            if len(fold_outputs) != len(variants)+1:
                continue
            for name, predicted in fold_outputs:
                for time in target:
                    predictions.append(dict(model=name, origin=fold_issue.isoformat(), time=time.isoformat(), actual=float(actual[time]), prediction=float(predicted[time]), baseline=float(baseline[time]), scale=float(scale) if np.isfinite(scale) and scale > 0 else None))
    metrics = []
    for model in dict.fromkeys(row["model"] for row in predictions):
        rows = [r for r in predictions if r["model"] == model]
        errors = np.array([r["actual"]-r["prediction"] for r in rows])
        scaled = [abs(r["actual"]-r["prediction"])/r["scale"] for r in rows if r["scale"]]
        metrics.append(dict(model=model, MAE=float(np.abs(errors).mean()), RMSE=float(np.sqrt((errors**2).mean())), MASE=float(np.mean(scaled)) if scaled else None, points=len(rows), matchedFolds=len({r["origin"] for r in rows})))
    report(1, "Experiment complete")
    return dict(kind="sarimax", config=c, aic=fitted["aic"] if np.isfinite(fitted["aic"]) else None, converged=fitted["converged"], warnings=fitted["warnings"], forecast=_rows(fitted["forecast"]), training=_rows(fitted["training"]), backtest=dict(metrics=metrics, predictions=predictions, failures=failures, attemptedFolds=c["folds"] if c["backtest"] else 0), metadata=dict(unit="kWh", issueTime=issue.isoformat(), lastAvailableEnergy=y.index[-1].isoformat(), trainingWindow={"start": c["start"], "end": c["end"]}, sourceVersions={"energy": energy.attrs.get("provenance"), "weather": weather.attrs.get("provenance")}, energyLagHours=c["energyLagHours"], weatherLagHours=c["weatherLagHours"], weatherMode="historical scenario: " + c["futureWeather"], uncertainty="Nominal 95% SARIMAX intervals conditional on fitted parameters and the chosen weather scenario; weather uncertainty is omitted. In-sample fitted/dynamic values are descriptive, not held-out forecasts.", interpretation="Retrospective experiment using latest revised snapshots and assumed publication lags, not an as-issued operational backtest. Compare held-out errors directly with seasonal naive; MASE below one alone does not establish improvement.", missingTargets=int(y.isna().sum()), missingPolicy="Regular UTC grid retained; missing training targets stay missing for state-space fitting, missing validation targets exclude the entire matched fold. Weather is projected from history available at each issue time."))
