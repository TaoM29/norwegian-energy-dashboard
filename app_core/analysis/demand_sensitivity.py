"""Calendar-adjusted household-demand/temperature associations.

The fixed 2021–2025 protocol selects a model on 2024 and evaluates once on
2025. Curves are contrasts against a reference temperature, averaged over the
same calendar design (which cancels in this additive model). They describe
conditional mean associations, not causal effects or prediction intervals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import SplineTransformer

from app_core.analysis.forecast_evaluation import _norwegian_holidays


@dataclass(frozen=True)
class DemandSensitivityConfig:
    start: str = "2021-01-01"
    train_end: str = "2024-01-01"
    validation_end: str = "2025-01-01"
    end: str = "2026-01-01"
    minimum_coverage: float = 0.95
    minimum_train: int = 10_000
    minimum_validation: int = 4_000
    minimum_test: int = 4_000
    ridge_alpha: float = 1.0
    minimum_improvement: float = 0.01
    minimum_absolute_improvement: float = 0.01  # kWh, guards near-zero MAE arithmetic
    grid_points: int = 41


def _timestamp(value: str) -> pd.Timestamp:
    result = pd.Timestamp(value)
    return result.tz_localize("UTC") if result.tz is None else result.tz_convert("UTC")


def _calendar(index: pd.DatetimeIndex, origin: pd.Timestamp, harmonics: int = 2) -> np.ndarray:
    local = index.tz_convert("Europe/Oslo")
    hour = np.asarray(local.hour)
    dow = np.asarray(local.dayofweek)
    holidays = set().union(*(_norwegian_holidays(y) for y in range(local.year.min(), local.year.max() + 1)))
    # Leap-year-specific denominators keep the seasonal phase within each
    # local calendar year; the UTC index remains the only temporal join key.
    day_phase = (np.asarray(local.dayofyear) - 1 + hour / 24) / np.where(local.is_leap_year, 366, 365)
    columns = [np.ones(len(index))]
    columns += [(hour == h).astype(float) for h in range(1, 24)]
    columns += [(dow == d).astype(float) for d in range(1, 7)]
    columns += [np.fromiter((date in holidays for date in local.date), dtype=float, count=len(index))]
    for harmonic in range(1, harmonics + 1):
        columns.extend([np.sin(2 * np.pi * harmonic * day_phase), np.cos(2 * np.pi * harmonic * day_phase)])
    columns += [(index - origin).total_seconds().to_numpy() / (365.2425 * 24 * 3600)]
    return np.column_stack(columns)


def _fit(x: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    gram = x.T @ x
    penalty = np.eye(x.shape[1]) * alpha
    penalty[0, 0] = 0  # Intercept is not regularized.
    bread = np.linalg.inv(gram + penalty)
    return bread @ (x.T @ y), bread


def _metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    residual = y - prediction
    return {"mae": float(np.mean(np.abs(residual))), "rmse": float(np.sqrt(np.mean(residual**2))),
            "bias": float(np.mean(residual)), "count": len(y)}


def _acf(values: np.ndarray, available: np.ndarray, lags: tuple[int, ...] = (1, 24, 168)) -> list[dict[str, Any]]:
    # Each lag pairs actual UTC slots; dropping gaps before shifting would
    # turn distant observations into misleading adjacent ones.
    output = []
    for lag in lags:
        valid = available[lag:] & available[:-lag]
        left, right = values[lag:][valid], values[:-lag][valid]
        correlation = float(np.corrcoef(left, right)[0, 1]) if len(left) >= 3 and np.std(left) > 0 and np.std(right) > 0 else None
        output.append({"lagHours": lag, "correlation": correlation, "pairs": int(valid.sum())})
    return output


def _hac_variances(scores: np.ndarray, max_lag: int) -> np.ndarray:
    """Bartlett Newey–West score covariance, with zero scores at absent UTC slots.

    FFT computes the *sum* of cross-products at each exact hourly lag; the
    ridge bread has already been applied to each score. This avoids treating
    consecutive complete cases separated by a data gap as adjacent hours.
    """
    size = len(scores)
    fft_size = 1 << (2 * size - 1).bit_length()
    spectra = np.fft.rfft(scores, n=fft_size, axis=0)
    autocov = np.fft.irfft(spectra * spectra.conj(), n=fft_size, axis=0)[:min(max_lag, size - 1) + 1]
    weights = 1 - np.arange(1, len(autocov)) / (max_lag + 1)
    variance = autocov[0] + 2 * np.sum(weights[:, None] * autocov[1:], axis=0)
    return np.maximum(variance, 0)


def analyze_area(frame: pd.DataFrame, area: str, config: DemandSensitivityConfig | None = None) -> dict[str, Any]:
    """Analyze hourly kWh demand against °C temperature on a regular UTC grid.

    ``frame`` has a UTC DatetimeIndex and ``demand``/``temperature`` columns.
    Nonfinite values remain absent throughout; no interpolation is performed.
    Override thresholds and dates via ``config`` for controlled tests, not to
    redefine the published production protocol. Raises ValueError on inadequate
    coverage or malformed input; the caller can report an unavailable area.
    """
    config = config or DemandSensitivityConfig()
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("frame must have a timezone-aware UTC DatetimeIndex")
    if str(frame.index.tz) != "UTC" or frame.index.has_duplicates:
        raise ValueError("frame index must be unique and UTC")
    if not {"demand", "temperature"}.issubset(frame.columns):
        raise ValueError("frame needs demand and temperature columns")
    start, train_end, validation_end, end = map(_timestamp, (config.start, config.train_end, config.validation_end, config.end))
    if not start < train_end < validation_end < end or config.grid_points < 3:
        raise ValueError("invalid temporal boundaries or curve grid")
    index = pd.date_range(start, end, freq="h", inclusive="left", tz="UTC")
    data = frame[["demand", "temperature"]].reindex(index).astype(float)
    values = data.to_numpy()
    present = np.isfinite(values).all(axis=1)
    boundaries = (("train", start, train_end, config.minimum_train),
                  ("validation", train_end, validation_end, config.minimum_validation),
                  ("test", validation_end, end, config.minimum_test))
    split_mask: dict[str, np.ndarray] = {}
    splits: dict[str, dict[str, Any]] = {}
    for name, left, right, minimum in boundaries:
        period = (index >= left) & (index < right)
        complete = period & present
        expected, observed = int(period.sum()), int(complete.sum())
        splits[name] = {"start": left.isoformat(), "end": right.isoformat(),
                        "expectedHours": expected, "observedHours": observed}
        split_mask[name] = complete
        if observed < minimum or observed / expected < config.minimum_coverage:
            raise ValueError(f"{area}: insufficient {name} complete-case coverage ({observed}/{expected}; minimum {minimum} and {config.minimum_coverage:.0%})")

    train = split_mask["train"]
    validation = split_mask["validation"]
    development = train | validation
    test = split_mask["test"]
    temp = values[:, 1]
    demand = values[:, 0]
    calendar = _calendar(index, start)
    # All preprocessing, including centering/scaling and spline knot placement,
    # is frozen on the training interval before validation is consulted.
    temperature_mean = float(np.mean(temp[train]))
    temperature_scale = max(float(np.std(temp[train])), 1e-8)
    linear_temp = np.zeros(len(index))
    linear_temp[present] = (temp[present] - temperature_mean) / temperature_scale
    design: dict[str, np.ndarray] = {"calendar": calendar, "linear": np.column_stack([calendar, linear_temp])}
    transformers: dict[int, SplineTransformer] = {}
    for knot_count in (4, 6):
        transformer = SplineTransformer(n_knots=knot_count, knots="quantile", degree=3,
                                        include_bias=False, extrapolation="constant")
        transformer.fit(temp[train, None])
        basis = np.zeros((len(index), transformer.n_features_out_))
        basis[present] = transformer.transform(temp[present, None])
        transformers[knot_count] = transformer
        design[f"spline{knot_count}"] = np.column_stack([calendar, basis])

    validation_fit: dict[str, dict[str, Any]] = {}
    for name, x in design.items():
        coefficient, _ = _fit(x[train], demand[train], config.ridge_alpha)
        validation_fit[name] = _metrics(demand[validation], x[validation] @ coefficient)
    def improves(candidate: float, baseline: float) -> bool:
        return baseline - candidate >= max(config.minimum_improvement * baseline,
                                           config.minimum_absolute_improvement)

    spline_knots = 6 if improves(validation_fit["spline6"]["mae"], validation_fit["spline4"]["mae"]) else 4
    spline_name = f"spline{spline_knots}"
    base_mae = validation_fit["calendar"]["mae"]
    linear_mae = validation_fit["linear"]["mae"]
    spline_mae = validation_fit[spline_name]["mae"]
    selected = "calendar"
    if improves(linear_mae, base_mae):
        selected = "linear"
    if improves(spline_mae, base_mae) and improves(spline_mae, linear_mae):
        selected = "spline"

    finalist = {"calendar": "calendar", "linear": "linear", "spline": spline_name}
    fitted: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    predictions: dict[str, np.ndarray] = {}
    models = []
    for family, name in finalist.items():
        x = design[name]
        fitted[family] = _fit(x[development], demand[development], config.ridge_alpha)
        predictions[family] = x[test] @ fitted[family][0]
        models.append({"model": family, "label": "Cubic spline" if family == "spline" else family.capitalize(),
                       "validation": validation_fit[name], "test": _metrics(demand[test], predictions[family]),
                       "parameters": {"ridgeAlpha": config.ridge_alpha,
                                      "splineKnots": spline_knots if family == "spline" else None,
                                      "calendarHarmonics": 2}})

    sorted_support = temp[development]
    low, high = (float(v) for v in np.quantile(sorted_support, [0.02, 0.98]))
    if high <= low:
        raise ValueError(f"{area}: temperature has no usable support")
    sorted_temperatures = np.sort(sorted_support)

    def local_count(temperatures: np.ndarray) -> np.ndarray:
        return (np.searchsorted(sorted_temperatures, temperatures + 0.5, side="right") -
                np.searchsorted(sorted_temperatures, temperatures - 0.5, side="left"))

    observed_central = sorted_temperatures[(sorted_temperatures >= low) & (sorted_temperatures <= high)]
    supported_observed = observed_central[local_count(observed_central) >= 30]
    if not len(supported_observed):
        raise ValueError(f"{area}: no temperature has at least 30 nearby development observations")
    reference = (5.0 if low <= 5 <= high and local_count(np.array([5.0]))[0] >= 30
                 else float(supported_observed[np.argmin(np.abs(supported_observed - np.median(sorted_support)))]))
    curve_temperatures = np.unique(np.r_[np.linspace(low, high, config.grid_points), reference])
    family = finalist[selected]
    coefficient, bread = fitted[selected]
    x = design[family]
    feature_count = x.shape[1]
    contrasts = np.zeros((len(curve_temperatures), feature_count))
    if selected == "linear":
        contrasts[:, -1] = (curve_temperatures - reference) / temperature_scale
    elif selected == "spline":
        transformer = transformers[spline_knots]
        contrasts[:, calendar.shape[1]:] = transformer.transform(curve_temperatures[:, None]) - transformer.transform(np.array([[reference]]))
    effects = contrasts @ coefficient
    # Sandwich score evaluated on the *regular* development grid; missing
    # response or temperature contributes a zero score at its original hour.
    residual = demand[development] - x[development] @ coefficient
    score_grid = np.zeros((len(index), len(curve_temperatures)))
    score_grid[development] = residual[:, None] * (x[development] @ bread @ contrasts.T)
    score_grid = score_grid[:int(np.flatnonzero(index >= validation_end)[0])]
    se168 = np.sqrt(_hac_variances(score_grid, 168))
    se336 = np.sqrt(_hac_variances(score_grid, 336))
    curve = []
    for i, t in enumerate(curve_temperatures):
        count = int(local_count(np.array([t]))[0])
        supported = bool(low <= t <= high and count >= 30)
        curve.append({"temperature": float(t), "effect": float(effects[i]) if supported else None,
                      "lower": float(effects[i] - 1.96 * se168[i]) if supported else None,
                      "upper": float(effects[i] + 1.96 * se168[i]) if supported else None,
                      "lower336": float(effects[i] - 1.96 * se336[i]) if supported else None,
                      "upper336": float(effects[i] + 1.96 * se336[i]) if supported else None,
                      "supported": supported,
                      "count": count})

    bin_edges = np.arange(np.floor(np.min(sorted_support)), np.ceil(np.max(sorted_support)) + 2)
    histogram, _ = np.histogram(sorted_support, bins=bin_edges)
    monthly = []
    local_month = np.asarray(index[development].tz_convert("Europe/Oslo").month)
    for month in range(1, 13):
        subset = sorted_support[local_month == month]
        monthly.append({"month": month, "count": len(subset),
                        "min": float(np.min(subset)) if len(subset) else None,
                        "max": float(np.max(subset)) if len(subset) else None})

    # Fixed selected temperature family; only annual calendar flexibility
    # changes. Both versions are refit on development, never selected on test.
    expanded_calendar = _calendar(index, start, harmonics=4)
    temp_features = x[development, calendar.shape[1]:]
    expanded_x = np.column_stack([expanded_calendar[development], temp_features])
    expanded_coefficient, _ = _fit(expanded_x, demand[development], config.ridge_alpha)
    expanded_contrast = np.zeros((len(curve_temperatures), expanded_x.shape[1]))
    expanded_contrast[:, expanded_calendar.shape[1]:] = contrasts[:, calendar.shape[1]:]
    supported_mask = np.array([point["supported"] for point in curve])
    expanded_effects = expanded_contrast @ expanded_coefficient
    max_difference = float(np.max(np.abs(effects[supported_mask] - expanded_effects[supported_mask])))

    test_index = index[test]
    test_residual = demand[test] - predictions[selected]
    residual_grid = np.zeros(len(index))
    residual_grid[test] = test_residual
    def group_error(groups: np.ndarray, key: str, possible: range) -> list[dict[str, Any]]:
        return [{key: int(group), "mean": float(np.mean(test_residual[groups == group])) if np.any(groups == group) else None,
                 "count": int(np.sum(groups == group))} for group in possible]

    local_test = test_index.tz_convert("Europe/Oslo")
    return {
        "area": area, "status": "ok", "selectedModel": selected, "referenceTemperature": reference,
        "curve": curve,
        "support": {"min": low, "max": high,
                    "bins": [{"temperature": float(edge + 0.5), "count": int(count)} for edge, count in zip(bin_edges[:-1], histogram)],
                    "byMonth": monthly},
        "models": models, "splits": splits,
        "residuals": {"acf": _acf(residual_grid, test),
                      "byHour": group_error(np.asarray(local_test.hour), "hour", range(24)),
                      "byMonth": group_error(np.asarray(local_test.month), "month", range(1, 13))},
        "sensitivity": {"maxCurveDifference": max_difference, "harmonics": 4,
                        "notes": "Selected temperature family refit with four rather than two annual Fourier harmonics on train+validation."},
        "predictions": [{"time": timestamp.isoformat(), "actual": float(actual),
                         **{name: float(predictions[name][i]) for name in finalist}}
                        for i, (timestamp, actual) in enumerate(zip(test_index, demand[test]))],
        "metadata": {"unit": "hourly household kWh", "temperatureUnit": "°C",
                     "interpretation": "Adjusted association in conditional mean, relative to reference temperature; not a causal or forecast effect.",
                     "curveCalendar": "Identical Oslo hour, weekday, holiday, annual season and trend at each contrasted temperature; additive calendar terms cancel.",
                     "uncertainty": "Approximate pointwise 95% fixed-model conditional-mean contrasts via ridge sandwich and Bartlett HAC on UTC hours (168 primary, 336 sensitivity); excludes ridge/smoothing bias, model selection, weather-proxy and specification uncertainty; not individual-hour prediction intervals.",
                     "selection": "Validation MAE; complexity requires at least 1% and 0.01 kWh improvement: 6 knots over 4, linear over calendar, spline over both simpler families. No test-based selection.",
                     "preprocessing": {"temperatureMeanTrain": temperature_mean, "temperatureScaleTrain": temperature_scale,
                                       "splineKnotVectorsTrainOnly": {str(k): [float(v) for v in transformer.bsplines_[0].t]
                                                                      for k, transformer in transformers.items()},
                                       "splineKnotsSelectedOnValidation": spline_knots, "completeCasesOnly": True},
                     "coefficients": {name: [float(v) for v in fitted[name][0]] for name in finalist},
                     "calendarDesign": "Intercept, Oslo hour 1–23 and weekday 1–6 dummies, public-holiday flag, annual Fourier harmonics 1–2, years-since-start trend.",
                     "ridgeAlpha": config.ridge_alpha, "support": "2nd–98th percentile of train+validation temperatures and at least 30 observations within ±0.5°C; unsupported curve suppressed.",
                     "limitations": "City-proxy temperature, remaining seasonal confounding, serial dependence and shared regional dates limit interpretation."},
    }
