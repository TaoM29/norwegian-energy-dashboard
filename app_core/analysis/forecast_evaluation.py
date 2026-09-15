"""Leakage-aware hourly household-demand benchmark evaluation.

The forecast ``origin`` is the UTC issue time and the start of horizon 1. Targets
cover origin through origin + horizon - 1 hours. Data availability is applied
before features are constructed: by default the latest usable Elhub and ERA5
intervals end 48 and 120 hours before origin. The currently published snapshots
contain later revisions, so results are retrospective and must not be described
as historical operational forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.statespace.sarimax import SARIMAX

from app_core.ingestion.models import AREAS


SCHEMA_VERSION = "1.0"
MODEL_NAMES = ("seasonal_naive", "ridge", "gradient_boosting", "sarimax")
WEATHER_MODES = ("historical_only", "realized_future_upper_bound")
WEATHER_COLUMNS = {
    "temperature_2m": ("temperature_2m", "temperature_2m (°C)"),
    "precipitation": ("precipitation", "precipitation (mm)"),
    "wind_speed_10m": ("wind_speed_10m", "wind_speed_10m (m/s)"),
}

DEFAULT_CONFIG: dict[str, Any] = {
    "areas": list(AREAS),
    "models": list(MODEL_NAMES),
    "horizon_hours": 24,
    "train_window_days": 120,
    "training_origin_stride_hours": 6,
    "validation_origins": ["2025-09-01T00:00:00Z", "2025-09-15T00:00:00Z"],
    "calibration_origins": ["2025-10-01T00:00:00Z", "2025-10-15T00:00:00Z"],
    "holdout_origins": ["2025-11-01T00:00:00Z", "2025-12-01T00:00:00Z"],
    "weather_mode": "historical_only",
    "energy_publication_lag_hours": 48,
    "weather_publication_lag_hours": 120,
    "interval_coverage": 0.80,
    "random_seed": 20250915,
    "ridge_alphas": [0.1, 1.0, 10.0],
    "gradient_boosting_candidates": [
        {"n_estimators": 120, "learning_rate": 0.05, "max_depth": 2},
        {"n_estimators": 160, "learning_rate": 0.04, "max_depth": 3},
    ],
    "sarimax_candidates": [
        {"order": [1, 0, 1], "seasonal_order": [0, 0, 0, 0]},
    ],
    "sarimax_maxiter": 75,
}

_CONFIG_KEYS = frozenset(DEFAULT_CONFIG)
_Progress = Callable[[float, str], None]
_Cancelled = Callable[[], bool]


class EvaluationCancelled(RuntimeError):
    """Raised when an evaluation job observes its cancellation callback."""


@dataclass
class _PreparedArea:
    energy: pd.Series
    weather: pd.DataFrame
    provenance: dict[str, Any]
    training_cache: dict[pd.Timestamp, tuple[pd.DataFrame, pd.Series]] = field(default_factory=dict)


def _utc_hour(value: Any, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
        timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field} must contain valid ISO timestamps") from error
    if pd.isna(timestamp) or timestamp != timestamp.floor("h"):
        raise ValueError(f"{field} timestamps must be aligned UTC hours")
    return timestamp


def _bounded_int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer from {low} to {high}")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer from {low} to {high}") from error
    if result != value or not low <= result <= high:
        raise ValueError(f"{field} must be an integer from {low} to {high}")
    return result


def _positive_numbers(values: Any, field: str, maximum_items: int = 12) -> list[float]:
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= maximum_items:
        raise ValueError(f"{field} must contain 1 to {maximum_items} positive numbers")
    result = [float(value) for value in values]
    if any(not math.isfinite(value) or value <= 0 for value in result):
        raise ValueError(f"{field} must contain positive finite numbers")
    return result


def _validate_gb_candidates(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 8:
        raise ValueError("gradient_boosting_candidates must contain 1 to 8 configurations")
    result = []
    for raw in values:
        if not isinstance(raw, Mapping) or set(raw) != {"n_estimators", "learning_rate", "max_depth"}:
            raise ValueError("each gradient boosting candidate needs n_estimators, learning_rate and max_depth")
        learning_rate = float(raw["learning_rate"])
        if not math.isfinite(learning_rate) or not 0.005 <= learning_rate <= 0.5:
            raise ValueError("gradient boosting learning_rate must be from 0.005 to 0.5")
        result.append({
            "n_estimators": _bounded_int(raw["n_estimators"], "n_estimators", 20, 500),
            "learning_rate": learning_rate,
            "max_depth": _bounded_int(raw["max_depth"], "max_depth", 1, 6),
        })
    return result


def _validate_sarimax_candidates(values: Any) -> list[dict[str, list[int]]]:
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 4:
        raise ValueError("sarimax_candidates must contain 1 to 4 configurations")
    result = []
    for raw in values:
        if not isinstance(raw, Mapping) or set(raw) != {"order", "seasonal_order"}:
            raise ValueError("each SARIMAX candidate needs order and seasonal_order")
        order, seasonal = raw["order"], raw["seasonal_order"]
        if not isinstance(order, (list, tuple)) or len(order) != 3:
            raise ValueError("SARIMAX order must have three integers")
        if not isinstance(seasonal, (list, tuple)) or len(seasonal) != 4:
            raise ValueError("SARIMAX seasonal_order must have four integers")
        checked_order = [_bounded_int(value, "SARIMAX order", 0, 3) for value in order]
        checked_seasonal = [_bounded_int(value, "SARIMAX seasonal order", 0, 2) for value in seasonal[:3]]
        period = _bounded_int(seasonal[3], "SARIMAX seasonal period", 0, 168)
        if period == 1 or (period == 0 and any(checked_seasonal)):
            raise ValueError("SARIMAX seasonal period must be 0 or at least 2")
        result.append({"order": checked_order, "seasonal_order": [*checked_seasonal, period]})
    return result


def validate_evaluation_config(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate and normalize the public benchmark configuration."""
    supplied = dict(config or {})
    unknown = sorted(set(supplied) - _CONFIG_KEYS)
    if unknown:
        raise ValueError(f"unknown evaluation config keys: {', '.join(unknown)}")
    merged = {**DEFAULT_CONFIG, **supplied}

    areas = list(dict.fromkeys(str(area).upper() for area in merged["areas"]))
    if not areas or any(area not in AREAS for area in areas):
        raise ValueError("areas must be a non-empty subset of NO1, NO2, NO3, NO4 and NO5")
    models = list(dict.fromkeys(str(model) for model in merged["models"]))
    if not models or any(model not in MODEL_NAMES for model in models):
        raise ValueError(f"models must be a non-empty subset of {', '.join(MODEL_NAMES)}")
    if "seasonal_naive" not in models:
        models.insert(0, "seasonal_naive")

    normalized: dict[str, Any] = {
        **merged,
        "areas": areas,
        "models": models,
        "horizon_hours": _bounded_int(merged["horizon_hours"], "horizon_hours", 1, 48),
        "train_window_days": _bounded_int(merged["train_window_days"], "train_window_days", 30, 365),
        "training_origin_stride_hours": _bounded_int(
            merged["training_origin_stride_hours"], "training_origin_stride_hours", 1, 24
        ),
        "energy_publication_lag_hours": _bounded_int(
            merged["energy_publication_lag_hours"], "energy_publication_lag_hours", 24, 168
        ),
        "weather_publication_lag_hours": _bounded_int(
            merged["weather_publication_lag_hours"], "weather_publication_lag_hours", 24, 240
        ),
        "random_seed": _bounded_int(merged["random_seed"], "random_seed", 0, 2**32 - 1),
        "ridge_alphas": _positive_numbers(merged["ridge_alphas"], "ridge_alphas"),
        "gradient_boosting_candidates": _validate_gb_candidates(merged["gradient_boosting_candidates"]),
        "sarimax_candidates": _validate_sarimax_candidates(merged["sarimax_candidates"]),
        "sarimax_maxiter": _bounded_int(merged["sarimax_maxiter"], "sarimax_maxiter", 5, 200),
    }
    coverage = float(merged["interval_coverage"])
    if not math.isfinite(coverage) or not 0.5 <= coverage < 1:
        raise ValueError("interval_coverage must be at least 0.5 and below 1")
    normalized["interval_coverage"] = coverage
    if merged["weather_mode"] not in WEATHER_MODES:
        if merged["weather_mode"] == "operational_forecast":
            raise ValueError("operational forecast weather is unavailable; archived issue-time forecasts are not ingested")
        raise ValueError(f"weather_mode must be one of {', '.join(WEATHER_MODES)}")

    stages: dict[str, list[pd.Timestamp]] = {}
    for key in ("validation_origins", "calibration_origins", "holdout_origins"):
        raw = merged[key]
        if not isinstance(raw, (list, tuple)) or not raw or len(raw) > 24:
            raise ValueError(f"{key} must contain 1 to 24 forecast origins")
        parsed = sorted(dict.fromkeys(_utc_hour(value, key) for value in raw))
        stages[key] = parsed
        normalized[key] = [value.isoformat().replace("+00:00", "Z") for value in parsed]
    if not max(stages["validation_origins"]) < min(stages["calibration_origins"]):
        raise ValueError("all validation origins must precede calibration origins")
    if not max(stages["calibration_origins"]) < min(stages["holdout_origins"]):
        raise ValueError("all calibration origins must precede holdout origins")
    label_delay = pd.Timedelta(
        hours=normalized["horizon_hours"] + normalized["energy_publication_lag_hours"]
    )
    if max(stages["validation_origins"]) + label_delay > min(stages["calibration_origins"]):
        raise ValueError("validation target labels must be available before calibration begins")
    if max(stages["calibration_origins"]) + label_delay > min(stages["holdout_origins"]):
        raise ValueError("calibration target labels must be available before holdout begins")
    return normalized


def _time_column(frame: pd.DataFrame) -> str:
    for candidate in ("timestamp", "time"):
        if candidate in frame:
            return candidate
    raise ValueError("frame needs a timestamp or time column")


def _value_column(frame: pd.DataFrame) -> str:
    for candidate in ("value", "quantity_kwh", "actual"):
        if candidate in frame:
            return candidate
    raise ValueError("energy frame needs a value or quantity_kwh column")


def regularize_hourly_frames(
    energy: pd.DataFrame,
    weather: pd.DataFrame,
    *,
    start: Any | None = None,
    end: Any | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Return a regular UTC grid without filling missing targets or weather."""
    if energy.empty:
        raise ValueError("energy frame is empty")
    e_time, e_value = _time_column(energy), _value_column(energy)
    e = energy[[e_time, e_value]].copy()
    e[e_time] = pd.to_datetime(e[e_time], utc=True, errors="coerce")
    e[e_value] = pd.to_numeric(e[e_value], errors="coerce")
    e = e.dropna(subset=[e_time]).groupby(e_time, sort=True)[e_value].sum(min_count=1)
    if e.index.duplicated().any():
        raise ValueError("energy timestamps must be unique after task filtering")

    w = pd.DataFrame()
    if not weather.empty:
        w_time = _time_column(weather)
        source_columns: dict[str, str] = {}
        for canonical, aliases in WEATHER_COLUMNS.items():
            found = next((alias for alias in aliases if alias in weather), None)
            if found:
                source_columns[canonical] = found
        raw = weather[[w_time, *source_columns.values()]].copy()
        raw[w_time] = pd.to_datetime(raw[w_time], utc=True, errors="coerce")
        raw = raw.dropna(subset=[w_time]).set_index(w_time).sort_index()
        if raw.index.duplicated().any():
            raise ValueError("weather timestamps must be unique after area filtering")
        w = raw.rename(columns={source: canonical for canonical, source in source_columns.items()})
        for column in w:
            w[column] = pd.to_numeric(w[column], errors="coerce")

    start_ts = _utc_hour(start, "start") if start is not None else e.index.min().floor("h")
    observed_ends = [e.index.max().floor("h")]
    if not w.empty:
        observed_ends.append(w.index.max().floor("h"))
    end_ts = _utc_hour(end, "end") if end is not None else max(observed_ends)
    if end_ts < start_ts:
        raise ValueError("regular grid end must not precede start")
    grid = pd.date_range(start_ts, end_ts, freq="h", tz="UTC")
    # Reindexing is deliberate: missing observations stay NaN.  There is no
    # interpolation, zero fill, backward fill, or access to a future value.
    return e.reindex(grid).astype(float), w.reindex(grid).astype(float)


def _norwegian_holidays(year: int) -> set[Any]:
    """Norwegian public-holiday dates needed as deterministic calendar features."""
    import datetime as _datetime

    # Anonymous Gregorian Easter algorithm.
    a, b = year % 19, year // 100
    c, d, e = year % 100, b // 4, b % 4
    f, g = (b + 8) // 25, (b - ((b + 8) // 25) + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    easter = _datetime.date(year, month, day)
    offsets = (-3, -2, 0, 1, 39, 49, 50)
    dates = {
        _datetime.date(year, 1, 1), _datetime.date(year, 5, 1),
        _datetime.date(year, 5, 17), _datetime.date(year, 12, 25),
        _datetime.date(year, 12, 26),
        *{easter + _datetime.timedelta(days=offset) for offset in offsets},
    }
    return dates


def _availability_cutoff(issue: pd.Timestamp, lag_hours: int) -> pd.Timestamp:
    """Start of latest usable interval when the lag is measured from its end."""
    return issue - pd.Timedelta(hours=int(lag_hours) + 1)


def _series_value(series: pd.Series, timestamp: pd.Timestamp) -> float:
    value = series.get(timestamp, np.nan)
    return float(value) if pd.notna(value) and np.isfinite(value) else np.nan


def _window_stats(series: pd.Series, end: pd.Timestamp, hours: int) -> tuple[float, float]:
    window = series.reindex(pd.date_range(end - pd.Timedelta(hours=hours - 1), end, freq="h", tz="UTC"))
    values = window.to_numpy(dtype=float)
    finite = np.isfinite(values)
    if finite.sum() < max(2, math.ceil(hours * 0.75)):
        return np.nan, np.nan
    return float(np.nanmean(values)), float(np.nanstd(values))


def _build_origin_features(
    energy: pd.Series,
    weather: pd.DataFrame,
    origin: Any,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Internal feature builder for an already normalized configuration."""
    cfg = config
    issue = _utc_hour(origin, "origin")
    energy_cutoff = _availability_cutoff(issue, cfg["energy_publication_lag_hours"])
    weather_cutoff = _availability_cutoff(issue, cfg["weather_publication_lag_hours"])
    energy_24_mean, energy_24_std = _window_stats(energy, energy_cutoff, 24)
    energy_168_mean, energy_168_std = _window_stats(energy, energy_cutoff, 168)

    holidays = _norwegian_holidays(issue.year) | _norwegian_holidays(issue.year + 1)
    weather_stats: dict[str, tuple[float, float]] = {}
    for column in WEATHER_COLUMNS:
        series = weather[column] if column in weather else pd.Series(dtype=float)
        weather_stats[column] = _window_stats(series, weather_cutoff, 24)

    rows = []
    for horizon in range(1, cfg["horizon_hours"] + 1):
        target = issue + pd.Timedelta(hours=horizon - 1)
        local_target = target.tz_convert("Europe/Oslo")
        row: dict[str, Any] = {
            "horizon": float(horizon),
            "hour_sin": math.sin(2 * math.pi * local_target.hour / 24),
            "hour_cos": math.cos(2 * math.pi * local_target.hour / 24),
            "dow_sin": math.sin(2 * math.pi * local_target.dayofweek / 7),
            "dow_cos": math.cos(2 * math.pi * local_target.dayofweek / 7),
            "year_sin": math.sin(2 * math.pi * (local_target.dayofyear - 1) / 365.25),
            "year_cos": math.cos(2 * math.pi * (local_target.dayofyear - 1) / 365.25),
            "is_weekend": float(local_target.dayofweek >= 5),
            "is_holiday_no": float(local_target.date() in holidays),
            "energy_available": _series_value(energy, energy_cutoff),
            "energy_available_lag_1": _series_value(energy, energy_cutoff - pd.Timedelta(hours=1)),
            "energy_available_lag_24": _series_value(energy, energy_cutoff - pd.Timedelta(hours=24)),
            "energy_available_lag_168": _series_value(energy, energy_cutoff - pd.Timedelta(hours=168)),
            "energy_roll_24_mean": energy_24_mean,
            "energy_roll_24_std": energy_24_std,
            "energy_roll_168_mean": energy_168_mean,
            "energy_roll_168_std": energy_168_std,
        }
        for column in WEATHER_COLUMNS:
            series = weather[column] if column in weather else pd.Series(dtype=float)
            if cfg["weather_mode"] == "realized_future_upper_bound":
                row[f"weather_{column}_realized_target"] = _series_value(series, target)
            else:
                row[f"weather_{column}_available"] = _series_value(series, weather_cutoff)
                row[f"weather_{column}_available_lag_24"] = _series_value(
                    series, weather_cutoff - pd.Timedelta(hours=24)
                )
                row[f"weather_{column}_roll_24_mean"] = weather_stats[column][0]
                row[f"weather_{column}_roll_24_std"] = weather_stats[column][1]
        rows.append(row)
    index = pd.date_range(issue, periods=cfg["horizon_hours"], freq="h", tz="UTC")
    return pd.DataFrame(rows, index=index, dtype=float)


def build_origin_features(
    energy: pd.Series,
    weather: pd.DataFrame,
    origin: Any,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Build the horizon feature rows using only data available at issue time."""
    return _build_origin_features(energy, weather, origin, validate_evaluation_config(config))


def build_training_matrix(
    energy: pd.Series,
    weather: pd.DataFrame,
    issue_origin: Any,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.Series]:
    """Construct a fold-local supervised sample; labels stop at issue availability."""
    cfg = validate_evaluation_config(config)
    issue = _utc_hour(issue_origin, "issue_origin")
    last_label = _availability_cutoff(issue, cfg["energy_publication_lag_hours"])
    first_origin = issue - pd.Timedelta(days=cfg["train_window_days"])
    last_origin = last_label - pd.Timedelta(hours=cfg["horizon_hours"] - 1)
    origins = pd.date_range(
        first_origin,
        last_origin,
        freq=f"{cfg['training_origin_stride_hours']}h",
        tz="UTC",
    )
    matrices: list[pd.DataFrame] = []
    labels: list[pd.Series] = []
    for historical_origin in origins:
        features = _build_origin_features(energy, weather, historical_origin, cfg)
        target = energy.reindex(features.index)
        keep = target.notna() & np.isfinite(target.to_numpy(dtype=float))
        if keep.any():
            matrices.append(features.loc[keep])
            labels.append(target.loc[keep])
    if not matrices:
        return pd.DataFrame(), pd.Series(dtype=float)
    X = pd.concat(matrices, axis=0, ignore_index=True)
    y = pd.concat(labels, axis=0, ignore_index=True).astype(float)
    return X, y


def _season(timestamp: pd.Timestamp) -> str:
    timestamp = timestamp.tz_convert("Europe/Oslo")
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}[timestamp.month]


def _is_peak(timestamp: pd.Timestamp) -> bool:
    timestamp = timestamp.tz_convert("Europe/Oslo")
    return bool(timestamp.dayofweek < 5 and (7 <= timestamp.hour < 10 or 16 <= timestamp.hour < 20))


def _mase_scale(training: pd.Series) -> float:
    if len(training) <= 168:
        return np.nan
    # Shift before dropping missing values so gaps do not compress time and
    # create pairs that were not actually 168 hours apart.
    differences = (training - training.shift(168)).abs().dropna()
    scale = float(differences.mean()) if len(differences) else np.nan
    return scale if np.isfinite(scale) and scale > 0 else np.nan


def _seasonal_naive(
    energy: pd.Series, targets: pd.DatetimeIndex, availability_cutoff: pd.Timestamp
) -> np.ndarray:
    values = []
    for target in targets:
        reference = target - pd.Timedelta(hours=168)
        while reference > availability_cutoff:
            reference -= pd.Timedelta(hours=168)
        values.append(_series_value(energy, reference))
    return np.asarray(values)


def _fit_tabular_model(
    model_name: str,
    parameters: Mapping[str, Any],
    energy: pd.Series,
    weather: pd.DataFrame,
    origin: pd.Timestamp,
    cfg: Mapping[str, Any],
    training_cache: dict[pd.Timestamp, tuple[pd.DataFrame, pd.Series]] | None = None,
) -> np.ndarray:
    if training_cache is not None and origin in training_cache:
        X_train, y_train = training_cache[origin]
    else:
        X_train, y_train = build_training_matrix(energy, weather, origin, cfg)
        if training_cache is not None:
            training_cache[origin] = (X_train, y_train)
    X_test = _build_origin_features(energy, weather, origin, cfg)
    if len(y_train) < 100 or y_train.nunique() < 2:
        raise ValueError("insufficient non-missing training observations")
    if model_name == "ridge":
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=float(parameters["alpha"]))),
        ])
        # Scaling the target is fitted inside this temporal fold as well.
        estimator = TransformedTargetRegressor(regressor=estimator, transformer=StandardScaler())
    elif model_name == "gradient_boosting":
        estimator = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", GradientBoostingRegressor(random_state=cfg["random_seed"], **dict(parameters))),
        ])
    else:
        raise ValueError(f"unsupported tabular model: {model_name}")
    estimator.fit(X_train, y_train)
    prediction = np.asarray(estimator.predict(X_test), dtype=float)
    if len(prediction) != cfg["horizon_hours"] or not np.isfinite(prediction).all():
        raise ValueError("model returned incomplete or non-finite predictions")
    return prediction


def _fit_sarimax(
    parameters: Mapping[str, Any],
    energy: pd.Series,
    origin: pd.Timestamp,
    cfg: Mapping[str, Any],
) -> np.ndarray:
    cutoff = _availability_cutoff(origin, cfg["energy_publication_lag_hours"])
    start = cutoff - pd.Timedelta(days=cfg["train_window_days"])
    y_train = energy.reindex(pd.date_range(start, cutoff, freq="h", tz="UTC"))
    if y_train.notna().sum() < max(168, int(len(y_train) * 0.75)):
        raise ValueError("insufficient non-missing SARIMAX training observations")
    observed = y_train.dropna()
    center, scale = float(observed.mean()), float(observed.std(ddof=0))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("SARIMAX training observations have zero or invalid scale")
    standardized = (y_train - center) / scale
    model = SARIMAX(
        standardized,
        order=tuple(parameters["order"]),
        seasonal_order=tuple(parameters["seasonal_order"]),
        enforce_stationarity=False,
        enforce_invertibility=False,
        freq="h",
    )
    fitted = model.fit(disp=False, maxiter=cfg["sarimax_maxiter"])
    if not bool(getattr(fitted, "mle_retvals", {}).get("converged", False)):
        raise ValueError("SARIMAX optimizer did not converge")
    steps = cfg["energy_publication_lag_hours"] + cfg["horizon_hours"]
    complete = np.asarray(fitted.get_forecast(steps=steps).predicted_mean, dtype=float)
    prediction = complete[-cfg["horizon_hours"]:] * scale + center
    if len(prediction) != cfg["horizon_hours"] or not np.isfinite(prediction).all():
        raise ValueError("SARIMAX returned incomplete or non-finite predictions")
    return prediction


def _candidate_parameters(model_name: str, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    if model_name == "seasonal_naive":
        return [{"seasonal_lag_hours": 168}]
    if model_name == "ridge":
        return [{"alpha": alpha} for alpha in cfg["ridge_alphas"]]
    if model_name == "gradient_boosting":
        return [dict(value) for value in cfg["gradient_boosting_candidates"]]
    return [dict(value) for value in cfg["sarimax_candidates"]]


def _predict(
    model_name: str,
    parameters: Mapping[str, Any],
    prepared: _PreparedArea,
    origin: pd.Timestamp,
    cfg: Mapping[str, Any],
) -> np.ndarray:
    targets = pd.date_range(origin, periods=cfg["horizon_hours"], freq="h", tz="UTC")
    if model_name == "seasonal_naive":
        prediction = _seasonal_naive(
            prepared.energy, targets,
            _availability_cutoff(origin, cfg["energy_publication_lag_hours"]),
        )
    elif model_name in {"ridge", "gradient_boosting"}:
        prediction = _fit_tabular_model(
            model_name, parameters, prepared.energy, prepared.weather, origin, cfg, prepared.training_cache
        )
    elif model_name == "sarimax":
        prediction = _fit_sarimax(parameters, prepared.energy, origin, cfg)
    else:
        raise ValueError(f"unknown model: {model_name}")
    if not np.isfinite(prediction).all():
        raise ValueError("required lagged observations are missing")
    return prediction


def _actuals(prepared: _PreparedArea, origin: pd.Timestamp, cfg: Mapping[str, Any]) -> tuple[pd.DatetimeIndex, np.ndarray]:
    targets = pd.date_range(origin, periods=cfg["horizon_hours"], freq="h", tz="UTC")
    actual = prepared.energy.reindex(targets).to_numpy(dtype=float)
    if not np.isfinite(actual).all():
        raise ValueError("one or more holdout targets are missing")
    return targets, actual


def _safe_reason(error: Exception) -> str:
    text = " ".join(str(error).split()) or error.__class__.__name__
    return text[:500]


def _check_cancelled(cancelled: _Cancelled | None) -> None:
    if cancelled is not None and cancelled():
        raise EvaluationCancelled("forecast evaluation cancelled")


def _notify(progress: _Progress | None, fraction: float, message: str) -> None:
    if progress is not None:
        progress(max(0.0, min(1.0, float(fraction))), message)


def _select_parameters(
    area: str,
    prepared: _PreparedArea,
    cfg: Mapping[str, Any],
    failures: list[dict[str, Any]],
    cancelled: _Cancelled | None,
) -> dict[str, dict[str, Any]]:
    origins = [_utc_hour(value, "validation_origins") for value in cfg["validation_origins"]]
    selected: dict[str, dict[str, Any]] = {}
    for model_name in cfg["models"]:
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for parameters in _candidate_parameters(model_name, cfg):
            errors: list[float] = []
            succeeded = 0
            for origin in origins:
                _check_cancelled(cancelled)
                try:
                    _, actual = _actuals(prepared, origin, cfg)
                    prediction = _predict(model_name, parameters, prepared, origin, cfg)
                    errors.extend(np.abs(actual - prediction).tolist())
                    succeeded += 1
                except Exception as error:
                    failures.append({
                        "area": area, "stage": "validation", "origin": origin.isoformat(),
                        "model": model_name, "parameters": _jsonable(parameters), "reason": _safe_reason(error),
                    })
            # Prefer configurations with complete validation coverage, then MAE.
            if succeeded:
                score = float(np.mean(errors)) + (len(origins) - succeeded) * 1e30
                scored.append((score, json.dumps(_jsonable(parameters), sort_keys=True), dict(parameters)))
        if not scored:
            raise ValueError(f"no {model_name} candidate succeeded on validation for {area}")
        selected[model_name] = min(scored, key=lambda value: (value[0], value[1]))[2]
    return selected


def _calibrate(
    area: str,
    prepared: _PreparedArea,
    selected: Mapping[str, Mapping[str, Any]],
    cfg: Mapping[str, Any],
    failures: list[dict[str, Any]],
    cancelled: _Cancelled | None,
) -> dict[str, dict[str, float]]:
    alpha = (1 - cfg["interval_coverage"]) / 2
    origins = [_utc_hour(value, "calibration_origins") for value in cfg["calibration_origins"]]
    residuals: dict[str, list[float]] = {model: [] for model in cfg["models"]}
    for origin in origins:
        try:
            _, actual = _actuals(prepared, origin, cfg)
        except Exception as error:
            for model_name in cfg["models"]:
                failures.append({"area": area, "stage": "calibration", "origin": origin.isoformat(),
                                 "model": model_name, "reason": _safe_reason(error)})
            continue
        for model_name in cfg["models"]:
            _check_cancelled(cancelled)
            try:
                prediction = _predict(model_name, selected[model_name], prepared, origin, cfg)
                residuals[model_name].extend((actual - prediction).tolist())
            except Exception as error:
                failures.append({"area": area, "stage": "calibration", "origin": origin.isoformat(),
                                 "model": model_name, "reason": _safe_reason(error)})
    result: dict[str, dict[str, float]] = {}
    for model_name, values in residuals.items():
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if not len(finite):
            raise ValueError(f"no calibration residuals for {area}/{model_name}")
        result[model_name] = {
            "lower_residual": float(np.quantile(finite, alpha)),
            "median_residual": float(np.quantile(finite, 0.5)),
            "upper_residual": float(np.quantile(finite, 1 - alpha)),
            "observations": int(len(finite)),
        }
    return result


def _pinball(actual: np.ndarray, forecast: np.ndarray, quantile: float) -> float:
    error = actual - forecast
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


def _metric_row(frame: pd.DataFrame, model: str, scope: str, **dimension: Any) -> dict[str, Any]:
    actual = frame["actual"].to_numpy(dtype=float)
    prediction = frame["prediction"].to_numpy(dtype=float)
    baseline = frame["baseline"].to_numpy(dtype=float)
    lower = frame["lower"].to_numpy(dtype=float)
    median = frame["median"].to_numpy(dtype=float)
    upper = frame["upper"].to_numpy(dtype=float)
    scales = frame["maseScale"].to_numpy(dtype=float)
    error = actual - prediction
    base_error = actual - baseline
    valid_scale = np.isfinite(scales) & (scales > 0)
    alpha = float(frame["lowerQuantile"].iloc[0])
    mae = float(np.mean(np.abs(error)))
    baseline_mae = float(np.mean(np.abs(base_error)))
    rmse = float(np.sqrt(np.mean(error**2)))
    baseline_rmse = float(np.sqrt(np.mean(base_error**2)))
    mase = float(np.mean(np.abs(error[valid_scale]) / scales[valid_scale])) if valid_scale.any() else None
    baseline_mase = (
        float(np.mean(np.abs(base_error[valid_scale]) / scales[valid_scale])) if valid_scale.any() else None
    )
    return {
        "scope": scope, **dimension, "model": model,
        "observations": int(len(frame)), "origins": int(frame["origin"].nunique()),
        "mae": mae, "rmse": rmse, "mase": mase,
        "baselineMae": baseline_mae, "baselineRmse": baseline_rmse, "baselineMase": baseline_mase,
        "maeDeltaVsBaseline": mae - baseline_mae,
        "maeRatioVsBaseline": mae / baseline_mae if baseline_mae > 0 else None,
        "rmseDeltaVsBaseline": rmse - baseline_rmse,
        "rmseRatioVsBaseline": rmse / baseline_rmse if baseline_rmse > 0 else None,
        "maseDeltaVsBaseline": mase - baseline_mase if mase is not None and baseline_mase is not None else None,
        "maseRatioVsBaseline": (
            mase / baseline_mase
            if mase is not None and baseline_mase is not None and baseline_mase > 0 else None
        ),
        "intervalCoverage": float(np.mean((actual >= lower) & (actual <= upper))),
        "meanIntervalWidth": float(np.mean(upper - lower)),
        "pinballLower": _pinball(actual, lower, alpha),
        "pinballMedian": _pinball(actual, median, 0.5),
        "pinballUpper": _pinball(actual, upper, 1 - alpha),
    }


def _metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not predictions:
        return []
    frame = pd.DataFrame(predictions)
    result: list[dict[str, Any]] = []
    for model, part in frame.groupby("model", sort=True):
        result.append(_metric_row(part, model, "overall"))
        for area, group in part.groupby("area", sort=True):
            result.append(_metric_row(group, model, "area", area=area))
        for season, group in part.groupby("season", sort=True):
            result.append(_metric_row(group, model, "season", season=season))
        for horizon, group in part.groupby("horizon", sort=True):
            result.append(_metric_row(group, model, "horizon", horizon=int(horizon)))
        for peak, group in part.groupby("isPeakPeriod", sort=True):
            result.append(_metric_row(group, model, "peak_period", isPeakPeriod=bool(peak)))
    return _jsonable(result)


def _frame_for_area(frame: pd.DataFrame, area: str) -> pd.DataFrame:
    if "area" not in frame:
        return frame.copy()
    return frame.loc[frame["area"].astype(str).str.upper() == area].copy()


def _prepare_area(energy: pd.DataFrame, weather: pd.DataFrame, area: str) -> _PreparedArea:
    energy_area = _frame_for_area(energy, area)
    if "kind" in energy_area:
        energy_area = energy_area.loc[energy_area["kind"].astype(str).str.lower() == "consumption"]
    if "group" in energy_area:
        energy_area = energy_area.loc[energy_area["group"].astype(str).str.lower() == "household"]
    weather_area = _frame_for_area(weather, area)
    provenance = {
        "energy": dict(energy_area.attrs.get("provenance", energy.attrs.get("provenance", {}))),
        "weather": dict(weather_area.attrs.get("provenance", weather.attrs.get("provenance", {}))),
    }
    energy_series, weather_frame = regularize_hourly_frames(energy_area, weather_area)
    return _PreparedArea(energy_series, weather_frame, provenance)


def _code_commit() -> str | None:
    root = Path(__file__).resolve().parents[2]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _feature_metadata(cfg: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "calendar": ["hour cyclic", "weekday cyclic", "annual cyclic", "weekend", "Norwegian public holiday"],
        "energy": {
            "availabilityCutoff": (
                f"interval ending {cfg['energy_publication_lag_hours']} hours before issue time; "
                "its stored interval start is one hour earlier"
            ),
            "lagsFromCutoffHours": [0, 1, 24, 168], "rollingWindowsHours": [24, 168],
        },
        "weather": {
            "mode": cfg["weather_mode"],
            "variables": list(WEATHER_COLUMNS),
            "availabilityCutoff": (
                f"interval ending {cfg['weather_publication_lag_hours']} hours before issue time"
                if cfg["weather_mode"] == "historical_only" else "realized target weather (upper bound)"
            ),
            "rollingWindowHours": [24] if cfg["weather_mode"] == "historical_only" else [],
        },
    }


def evaluate_frames(
    energy: pd.DataFrame,
    weather: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    progress: _Progress | None = None,
    cancelled: _Cancelled | None = None,
) -> dict[str, Any]:
    """Run tuning, calibration and untouched holdout evaluation on supplied frames."""
    cfg = validate_evaluation_config(config)
    failures: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    selected_all: dict[str, dict[str, Any]] = {}
    calibration_all: dict[str, dict[str, Any]] = {}
    coverage_areas: list[dict[str, Any]] = []
    units = max(1, len(cfg["areas"]) * 3)
    completed = 0

    for area in cfg["areas"]:
        _check_cancelled(cancelled)
        prepared = _prepare_area(energy, weather, area)
        _notify(progress, completed / units, f"Selecting {area} model parameters on validation origins")
        selected = _select_parameters(area, prepared, cfg, failures, cancelled)
        selected_all[area] = _jsonable(selected)
        completed += 1

        _notify(progress, completed / units, f"Calibrating {area} intervals before holdout")
        calibration = _calibrate(area, prepared, selected, cfg, failures, cancelled)
        calibration_all[area] = _jsonable(calibration)
        completed += 1

        attempted = len(cfg["holdout_origins"])
        matched = 0
        successful_by_model = {model: 0 for model in cfg["models"]}
        excluded: list[str] = []
        for origin_raw in cfg["holdout_origins"]:
            _check_cancelled(cancelled)
            origin = _utc_hour(origin_raw, "holdout_origins")
            origin_predictions: dict[str, np.ndarray] = {}
            origin_failed = False
            try:
                targets, actual = _actuals(prepared, origin, cfg)
            except Exception as error:
                for model_name in cfg["models"]:
                    failures.append({"area": area, "stage": "holdout", "origin": origin.isoformat(),
                                     "model": model_name, "reason": _safe_reason(error)})
                origin_failed = True
                targets = pd.DatetimeIndex([])
                actual = np.asarray([])
            if not origin_failed:
                for model_name in cfg["models"]:
                    try:
                        origin_predictions[model_name] = _predict(
                            model_name, selected[model_name], prepared, origin, cfg
                        )
                        successful_by_model[model_name] += 1
                    except Exception as error:
                        origin_failed = True
                        failures.append({"area": area, "stage": "holdout", "origin": origin.isoformat(),
                                         "model": model_name, "reason": _safe_reason(error)})
            if origin_failed:
                excluded.append(origin.isoformat())
                continue
            matched += 1
            baseline = origin_predictions["seasonal_naive"]
            train_cutoff = _availability_cutoff(origin, cfg["energy_publication_lag_hours"])
            train_start = train_cutoff - pd.Timedelta(days=cfg["train_window_days"])
            scale = _mase_scale(prepared.energy.loc[train_start:train_cutoff])
            lower_quantile = (1 - cfg["interval_coverage"]) / 2
            for model_name, values in origin_predictions.items():
                interval = calibration[model_name]
                for offset, target in enumerate(targets):
                    prediction = float(values[offset])
                    predictions.append({
                        "area": area, "cohort": "matched_holdout", "origin": origin.isoformat(),
                        "targetTime": target.isoformat(), "horizon": offset + 1, "model": model_name,
                        "actual": float(actual[offset]), "prediction": prediction,
                        "lower": prediction + interval["lower_residual"],
                        "median": prediction + interval["median_residual"],
                        "upper": prediction + interval["upper_residual"],
                        "lowerQuantile": lower_quantile, "upperQuantile": 1 - lower_quantile,
                        "baseline": float(baseline[offset]), "maseScale": scale,
                        "season": _season(target), "isPeakPeriod": _is_peak(target),
                    })
        coverage_areas.append({
            "area": area, "attemptedOrigins": attempted, "matchedOrigins": matched,
            "excludedOrigins": excluded, "successfulOriginsByModel": successful_by_model,
        })
        completed += 1
        _notify(progress, completed / units, f"Completed matched holdout evaluation for {area}")

    assumptions = {
        "issueTime": (
            "UTC forecast issuance at the start of the first target interval; horizons 1..H cover interval starts "
            "from issue time through issue time plus H-1 hours."
        ),
        "energyAvailability": (
            f"The last usable household-demand interval ends {cfg['energy_publication_lag_hours']} hours before issue time."
        ),
        "weatherAvailability": (
            f"The last usable ERA5 interval ends {cfg['weather_publication_lag_hours']} hours before issue time."
            if cfg["weather_mode"] == "historical_only"
            else "Realized weather at each target is used as an explicitly labelled upper-bound experiment."
        ),
        "snapshotCaveat": (
            "Elhub and ERA5 inputs are current published snapshots that may include revisions. Availability cutoffs are "
            "simulated retrospectively; results are not evidence of historical operational forecast performance."
        ),
        "operationalWeather": "Archived issue-time operational weather forecasts are not currently ingested.",
        "intervals": (
            "Empirical signed-residual quantiles are calibrated only on pre-holdout origins. They condition on the "
            "selected weather experiment and do not model weather forecast uncertainty."
        ),
        "matchedCohort": "Metrics include only holdout origins where every requested model and the baseline succeeded.",
        "rollingRefit": (
            "Each holdout origin is refitted causally using labels published by that issue time. Earlier holdout labels "
            "may enter later fits after their publication lag, but never parameter selection or interval calibration."
        ),
    }
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "experiment": "household_demand_24h_flagship",
        "config": cfg,
        "metadata": {
            "task": "Hourly household electricity demand for all selected Norwegian price areas",
            "unit": "kWh", "timezone": "UTC", "codeCommit": _code_commit(),
            "trainingWindows": {"days": cfg["train_window_days"], "originStrideHours": cfg["training_origin_stride_hours"]},
            "features": _feature_metadata(cfg), "assumptions": assumptions,
        },
        "selectedParameters": selected_all,
        "calibration": calibration_all,
        "origins": {
            "validation": cfg["validation_origins"], "calibration": cfg["calibration_origins"],
            "holdout": cfg["holdout_origins"], "selectionFrozenBeforeHoldout": True,
        },
        "predictions": _jsonable(predictions),
        "failures": _jsonable(failures),
        "metrics": _metrics(predictions),
        "coverage": {
            "requestedModels": cfg["models"], "areas": coverage_areas,
            "attemptedOrigins": sum(row["attemptedOrigins"] for row in coverage_areas),
            "matchedOrigins": sum(row["matchedOrigins"] for row in coverage_areas),
            "failedOrigins": sum(row["attemptedOrigins"] - row["matchedOrigins"] for row in coverage_areas),
        },
    }
    _notify(progress, 1.0, "Forecast evaluation complete")
    return _jsonable(result)


def _date_chunks(start: pd.Timestamp, end: pd.Timestamp) -> Iterable[tuple[pd.Timestamp, pd.Timestamp]]:
    cursor = start
    while cursor < end:
        chunk_end = min(end, cursor + pd.Timedelta(days=366))
        yield cursor, chunk_end
        cursor = chunk_end


def _load_frames(config: Mapping[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    from backend import data as backend_data

    all_origins = [
        _utc_hour(value, "origin")
        for key in ("validation_origins", "calibration_origins", "holdout_origins")
        for value in config[key]
    ]
    lookback_hours = max(168 + config["energy_publication_lag_hours"], 24 + config["weather_publication_lag_hours"])
    start = min(all_origins) - pd.Timedelta(days=config["train_window_days"], hours=lookback_hours)
    end = max(all_origins) + pd.Timedelta(hours=config["horizon_hours"] + 1)
    energy_parts: list[pd.DataFrame] = []
    weather_parts: list[pd.DataFrame] = []
    provenance: dict[str, Any] = {"areas": {}}
    for area in config["areas"]:
        area_energy: list[pd.DataFrame] = []
        area_weather: list[pd.DataFrame] = []
        area_provenance: dict[str, Any] = {"energy": [], "weather": []}
        for chunk_start, chunk_end in _date_chunks(start, end):
            e = backend_data.energy_frame(
                area, chunk_start, chunk_end, kind="consumption", groups=["household"]
            )
            w = backend_data.weather_frame(area, chunk_start, chunk_end)
            area_provenance["energy"].append(dict(e.attrs.get("provenance", {})))
            area_provenance["weather"].append(dict(w.attrs.get("provenance", {})))
            area_energy.append(e)
            area_weather.append(w)
        joined_energy = pd.concat(area_energy, ignore_index=True)
        joined_weather = pd.concat(area_weather, ignore_index=True)
        joined_energy["area"] = area
        joined_weather["area"] = area
        energy_parts.append(joined_energy)
        weather_parts.append(joined_weather)
        provenance["areas"][area] = area_provenance
    return pd.concat(energy_parts, ignore_index=True), pd.concat(weather_parts, ignore_index=True), provenance


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def run_evaluation(
    config: Mapping[str, Any] | None = None,
    progress: _Progress | None = None,
    cancelled: _Cancelled | None = None,
) -> dict[str, Any]:
    """Load published snapshots and run the flagship evaluation synchronously."""
    cfg = validate_evaluation_config(config)
    _check_cancelled(cancelled)
    _notify(progress, 0.0, "Loading published household demand and ERA5 snapshots")
    energy, weather, dataset_version = _load_frames(cfg)
    _check_cancelled(cancelled)
    result = evaluate_frames(energy, weather, cfg, progress=progress, cancelled=cancelled)
    result["metadata"]["datasetVersion"] = _jsonable(dataset_version)
    return result


__all__ = [
    "DEFAULT_CONFIG", "EvaluationCancelled", "MODEL_NAMES", "WEATHER_MODES",
    "build_origin_features", "build_training_matrix", "evaluate_frames",
    "regularize_hourly_frames", "run_evaluation", "validate_evaluation_config",
]
