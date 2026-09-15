from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app_core.analysis.data_quality import lof_precip_anomalies, spc_outliers_dct
from app_core.analysis.sliding_correlation import (
    align_two_series,
    apply_lag_hours,
    rolling_pearson_corr,
)
from app_core.analysis.spectrogram import production_spectrogram
from app_core.analysis.stats_utils import zscore
from app_core.analysis.stl import stl_decompose_elhub
from app_core.ingestion.models import AREAS, BASE_GROUPS
from app_core.loaders.weather import OUTPUT_COLUMNS
from backend.data import energy_frame, provenance, validate_range, weather_frame


router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

WEATHER_FIELDS = tuple(OUTPUT_COLUMNS.values())
WEATHER_UNITS = {
    "temperature_2m (°C)": "°C",
    "precipitation (mm)": "mm",
    "wind_speed_10m (m/s)": "m/s",
    "wind_gusts_10m (m/s)": "m/s",
    "wind_direction_10m (°)": "°",
}
MAX_LINE_POINTS = 1_500
MAX_SPECTRAL_TIMES = 320
MAX_SPECTRAL_FREQUENCIES = 193


def _range(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    try:
        return validate_range(start, end, max_days=366)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _check_area(area: str) -> str:
    area = area.upper()
    if area not in AREAS:
        raise HTTPException(status_code=422, detail=f"area must be one of {', '.join(AREAS)}")
    return area


def _check_group(kind: str, group: str) -> None:
    if group not in BASE_GROUPS[kind]:
        allowed = ", ".join(BASE_GROUPS[kind])
        raise HTTPException(status_code=422, detail=f"group must be one of {allowed} for {kind}")


def _energy_series(frame: pd.DataFrame) -> pd.Series:
    """Adapt the shared long energy frame to a unique hourly kWh series."""
    time_col = next((name for name in ("time", "timestamp", "start_time") if name in frame), None)
    value_col = next((name for name in ("value", "quantity_kwh", "value_kwh") if name in frame), None)
    if time_col is None or value_col is None:
        raise HTTPException(status_code=500, detail="Energy data does not match the analytical schema.")
    data = frame[[time_col, value_col]].copy()
    data[time_col] = pd.to_datetime(data[time_col], utc=True, errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=[time_col]).sort_values(time_col)
    return data.set_index(time_col)[value_col].resample("h").sum(min_count=1).asfreq("h")


def _weather_series(frame: pd.DataFrame, field: str) -> pd.Series:
    if "time" not in frame or field not in frame:
        raise HTTPException(status_code=500, detail=f"Weather data is missing {field}.")
    data = frame[["time", field]].copy()
    data["time"] = pd.to_datetime(data["time"], utc=True, errors="coerce")
    data[field] = pd.to_numeric(data[field], errors="coerce")
    data = data.dropna(subset=["time"]).sort_values("time")
    return data.set_index("time")[field].resample("h").mean().asfreq("h")


def _json_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat().replace("+00:00", "Z")


def _safe_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return _iso(value)
    if isinstance(value, np.generic):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _frame_metadata(frame: pd.DataFrame) -> dict:
    return _safe_metadata(frame.attrs.get("provenance", frame.attrs))


def _sample_indices(length: int, limit: int, required: np.ndarray | None = None) -> np.ndarray:
    if length <= limit:
        return np.arange(length, dtype=int)
    if required is not None and required.size:
        required = np.unique(required)
        if len(required) >= limit:
            return required[np.linspace(0, len(required) - 1, limit, dtype=int)]
        base = np.linspace(0, length - 1, limit - len(required), dtype=int)
        return np.unique(np.concatenate((base, required)))
    return np.linspace(0, length - 1, limit, dtype=int)


def _line_rows(frame: pd.DataFrame, fields: tuple[str, ...], *, flags: str | None = None) -> list[dict]:
    required = None
    if flags and flags in frame:
        required = np.flatnonzero(frame[flags].fillna(False).to_numpy(dtype=bool))
    selected = frame.iloc[_sample_indices(len(frame), MAX_LINE_POINTS, required)]
    rows: list[dict] = []
    for _, row in selected.iterrows():
        item: dict[str, Any] = {"time": _iso(row["time"])}
        for field in fields:
            value = row[field]
            item[field] = bool(value) if field == flags else _json_number(value)
        rows.append(item)
    return rows


def _base_metadata(area: str, start: str, end: str, *, analyzed: int, returned: int) -> dict:
    return {
        "interval": {"start": start, "end": end, "bounds": "UTC half-open [start, end)"},
        "aggregation": "hourly",
        "analyzedPoints": analyzed,
        "returnedChartPoints": returned,
        "chartPayloadLimited": returned < analyzed,
        "provenance": provenance(area, start, end),
    }


@router.get("/correlation")
def correlation(
    area: str = "NO1",
    start: str = Query(...),
    end: str = Query(...),
    kind: Literal["production", "consumption"] = "production",
    group: str = "hydro",
    weather: str = "temperature_2m (°C)",
    window_hours: int = Query(168, ge=12, le=720, alias="windowHours"),
    lag_hours: int = Query(0, ge=-240, le=240, alias="lagHours"),
    normalize: bool = True,
) -> dict:
    area = _check_area(area)
    _check_group(kind, group)
    if weather not in WEATHER_FIELDS:
        raise HTTPException(status_code=422, detail="Unsupported weather variable.")
    start_ts, end_ts = _range(start, end)

    energy_data = energy_frame(area, start_ts, end_ts, kind=kind, groups=[group])
    weather_data = weather_frame(area, start_ts, end_ts)
    energy = _energy_series(energy_data)
    weather_values = _weather_series(weather_data, weather)
    wx, en = align_two_series(apply_lag_hours(weather_values, lag_hours), energy)
    if len(wx) < window_hours:
        raise HTTPException(
            status_code=422,
            detail=f"The selected lag leaves {len(wx)} paired hours; the {window_hours}-hour window needs at least {window_hours}.",
        )

    correlation_values = rolling_pearson_corr(wx, en, window_hours, center=True, min_periods=window_hours)
    wx_plot = zscore(wx) if normalize else wx
    en_plot = zscore(en) if normalize else en
    values = pd.DataFrame(
        {
            "time": wx.index,
            "weather": wx_plot.to_numpy(),
            "energy": en_plot.to_numpy(),
            "correlation": correlation_values.to_numpy(),
        }
    )
    chart = _line_rows(values, ("weather", "energy", "correlation"))
    valid_corr = correlation_values.dropna()
    return {
        "query": {
            "area": area,
            "start": start,
            "end": end,
            "kind": kind,
            "group": group,
            "weather": weather,
            "windowHours": window_hours,
            "lagHours": lag_hours,
            "normalize": normalize,
        },
        "units": {
            "weather": "z-score" if normalize else WEATHER_UNITS[weather],
            "energy": "z-score" if normalize else "kWh",
            "correlation": "Pearson r",
        },
        "summary": {
            "pairedHours": len(values),
            "correlationHours": len(valid_corr),
            "meanCorrelation": _json_number(valid_corr.mean()),
            "latestCorrelation": _json_number(valid_corr.iloc[-1]) if not valid_corr.empty else None,
        },
        "values": chart,
        "metadata": {
            **_base_metadata(area, start, end, analyzed=len(values), returned=len(chart)),
            "lagConvention": "Positive lag shifts weather forward in time, testing whether weather leads energy.",
            "correlation": "Centered rolling Pearson correlation requiring a complete window.",
            "normalization": "Population z-scores affect the comparison chart only; correlation uses original values.",
            "missingData": "Hourly means for weather and sums for energy; only observed pairs are analyzed. Missing values are not replaced with zero.",
            "coverage": {
                "expectedHours": int((end_ts - start_ts).total_seconds() / 3600),
                "energyObservedHours": int(energy.notna().sum()),
                "weatherObservedHours": int(weather_values.notna().sum()),
                "pairedHours": len(values),
            },
            "sources": {"energy": _frame_metadata(energy_data), "weather": _frame_metadata(weather_data)},
            "interpretation": (
                "Wind direction is circular; linear Pearson correlation near the 0°/360° boundary can mislead."
                if weather == "wind_direction_10m (°)"
                else "Correlation describes linear association and does not establish causation."
            ),
        },
    }


@router.get("/decomposition")
def decomposition(
    area: str = "NO1",
    start: str = Query(...),
    end: str = Query(...),
    kind: Literal["production", "consumption"] = "production",
    group: str = "solar",
    period: int = Query(24, ge=2, le=2_000),
    seasonal_smoother: int = Query(13, ge=3, le=9_999, alias="seasonalSmoother"),
    trend_smoother: int = Query(365, ge=3, le=9_999, alias="trendSmoother"),
    robust: bool = True,
    spectrogram_window: int = Query(168, ge=8, le=4_096, alias="spectrogramWindow"),
    spectrogram_overlap: int = Query(84, ge=0, le=4_095, alias="spectrogramOverlap"),
) -> dict:
    area = _check_area(area)
    _check_group(kind, group)
    start_ts, end_ts = _range(start, end)
    if spectrogram_overlap >= spectrogram_window:
        raise HTTPException(status_code=422, detail="Spectrogram overlap must be smaller than its window.")

    source = energy_frame(area, start_ts, end_ts, kind=kind, groups=[group])
    series = _energy_series(source)
    if series.empty:
        raise HTTPException(status_code=404, detail="No energy observations match this selection.")
    if series.isna().any():
        raise HTTPException(status_code=422, detail="STL and the spectrogram require complete hourly observations; missing hours are not filled with zero.")
    if len(series) < max(period * 2, spectrogram_window):
        raise HTTPException(
            status_code=422,
            detail=f"This setup needs at least {max(period * 2, spectrogram_window)} complete hours; only {len(series)} are available.",
        )

    group_col = "production_group" if kind == "production" else "consumption_group"
    helper_frame = pd.DataFrame(
        {
            "price_area": area,
            group_col: group,
            "start_time": series.index,
            "quantity_kwh": series.to_numpy(),
        }
    )
    try:
        figures, details, _ = stl_decompose_elhub(
            helper_frame,
            area=area,
            group=group,
            period=period,
            seasonal=seasonal_smoother,
            trend=trend_smoother,
            robust=robust,
            group_col=group_col,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Invalid STL parameter combination: {error}") from error
    if "error" in details:
        raise HTTPException(status_code=422, detail=details["error"])
    components = {
        name: pd.Series(figure.data[0].y, index=pd.to_datetime(figure.data[0].x, utc=True))
        for name, figure in figures.items()
    }
    component_frame = pd.DataFrame({"time": series.index, **components})
    component_rows = _line_rows(component_frame, ("observed", "seasonal", "trend", "resid"))

    try:
        _, frequencies, spectral_times, magnitude = production_spectrogram(
            helper_frame,
            area=area,
            group=group,
            window_len=spectrogram_window,
            overlap=spectrogram_overlap,
            group_col=group_col,
            freq_units="cpd",
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Invalid spectrogram parameter combination: {error}") from error
    if frequencies is None or spectral_times is None or magnitude is None:
        raise HTTPException(status_code=422, detail="The spectrogram could not be computed for this selection.")
    frequencies_cpd = frequencies * 24.0
    visible = np.flatnonzero(frequencies_cpd <= 12.0)
    frequency_idx = visible[_sample_indices(len(visible), MAX_SPECTRAL_FREQUENCIES)]
    time_idx = _sample_indices(len(spectral_times), MAX_SPECTRAL_TIMES)
    matrix = magnitude[np.ix_(frequency_idx, time_idx)]

    return {
        "query": {
            "area": area,
            "start": start,
            "end": end,
            "kind": kind,
            "group": group,
            "period": period,
            "seasonalSmoother": seasonal_smoother,
            "trendSmoother": trend_smoother,
            "robust": robust,
            "spectrogramWindow": spectrogram_window,
            "spectrogramOverlap": spectrogram_overlap,
        },
        "units": {"components": "kWh", "spectrogramFrequency": "cycles/day", "spectrogramMagnitude": "|X|"},
        "effectiveParameters": {
            "period": details["period"],
            "seasonalSmoother": details["seasonal"],
            "trendSmoother": details["trend"],
            "robust": details["robust"],
            "spectrogramWindow": spectrogram_window,
            "spectrogramOverlap": spectrogram_overlap,
        },
        "components": component_rows,
        "spectrogram": {
            "times": [_iso(spectral_times[index]) for index in time_idx],
            "frequencies": [round(float(frequencies_cpd[index]), 8) for index in frequency_idx],
            "magnitude": [[_json_number(value) for value in row] for row in matrix],
        },
        "metadata": {
            **_base_metadata(area, start, end, analyzed=len(series), returned=len(component_rows)),
            "missingData": "Both analyses require unique, complete hourly values. Missing hours are rejected rather than treated as zero.",
            "spectrogram": "Hann window, linear detrending, density scaling and magnitude mode; displayed frequencies are limited to 0–12 cycles/day.",
            "spectrogramShapeAnalyzed": [int(len(frequencies)), int(len(spectral_times))],
            "spectrogramShapeReturned": [int(len(frequency_idx)), int(len(time_idx))],
            "coverage": {
                "expectedHours": int((end_ts - start_ts).total_seconds() / 3600),
                "observedHours": int(series.notna().sum()),
            },
            "sources": {"energy": _frame_metadata(source)},
        },
    }


@router.get("/quality")
def quality(
    area: str = "NO1",
    start: str = Query(...),
    end: str = Query(...),
    dct_fraction: float = Query(0.01, ge=0.001, le=0.05, alias="dctFraction"),
    k: float = Query(3.0, ge=1.0, le=6.0),
    contamination: float = Query(0.01, ge=0.001, le=0.05),
    neighbors: int = Query(60, ge=10, le=120),
) -> dict:
    area = _check_area(area)
    start_ts, end_ts = _range(start, end)
    weather = weather_frame(area, start_ts, end_ts).copy()
    if weather.empty:
        raise HTTPException(status_code=404, detail="No weather observations match this selection.")
    weather["time"] = pd.to_datetime(weather["time"], utc=True, errors="coerce")
    weather = weather.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    temperature_field = "temperature_2m (°C)"
    precipitation_field = "precipitation (mm)"

    temperature = _weather_series(weather, temperature_field)
    spc, spc_summary = spc_outliers_dct(
        temperature,
        keep_frac=dct_fraction,
        k_sigma=k,
        interp_limit=6,
    )
    if spc.empty:
        raise HTTPException(status_code=422, detail="SPC needs at least 24 observed temperature values.")
    spc_chart = _line_rows(spc, ("value", "trend", "lo", "hi", "satv", "is_outlier"), flags="is_outlier")
    spc_flags = _line_rows(spc.loc[spc["is_outlier"]], ("value", "trend", "lo", "hi", "satv", "is_outlier"), flags="is_outlier")

    precipitation = pd.to_numeric(weather[precipitation_field], errors="coerce")
    if precipitation.isna().any():
        raise HTTPException(status_code=422, detail="LOF requires observed precipitation; missing rainfall is not treated as zero.")
    if int((precipitation > 0).sum()) < 10:
        raise HTTPException(status_code=422, detail="LOF needs at least 10 positive-precipitation hours.")
    try:
        lof, effective_neighbors = lof_precip_anomalies(
            weather,
            time_col="time",
            precip_col=precipitation_field,
            contamination=contamination,
            n_neighbors=neighbors,
            roll_hours=24,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    lof_chart = _line_rows(lof, ("precip", "roll24", "lof_score", "is_anom"), flags="is_anom")
    lof_flags = _line_rows(lof.loc[lof["is_anom"]], ("precip", "roll24", "lof_score", "is_anom"), flags="is_anom")

    return {
        "query": {
            "area": area,
            "start": start,
            "end": end,
            "dctFraction": dct_fraction,
            "k": k,
            "contamination": contamination,
            "neighbors": neighbors,
        },
        "units": {"temperature": "°C", "precipitation": "mm", "satv": "robust standard deviations", "lofScore": "unitless"},
        "spc": {
            "summary": {
                "points": spc_summary.n_points,
                "flags": spc_summary.n_outliers,
                "flagPercent": round(100 * spc_summary.n_outliers / spc_summary.n_points, 4),
                "robustSigma": spc_summary.sigma_robust,
                "keptCoefficients": spc_summary.keep_k,
                "maxAbsSatv": spc_summary.max_abs_satv,
            },
            "values": spc_chart,
            "flaggedValues": spc_flags,
        },
        "lof": {
            "summary": {
                "points": len(lof),
                "flags": int(lof["is_anom"].sum()),
                "flagPercent": round(100 * int(lof["is_anom"].sum()) / len(lof), 4),
                "effectiveNeighbors": effective_neighbors,
            },
            "values": lof_chart,
            "flaggedValues": lof_flags,
        },
        "metadata": {
            **_base_metadata(area, start, end, analyzed=len(weather), returned=max(len(spc_chart), len(lof_chart))),
            "interpretation": "Flags are statistical candidates for inspection, not verified data faults. Real weather extremes can be flagged.",
            "spcMissingData": "Hourly temperature gaps up to six hours are interpolated; remaining edge or long gaps use the nearest observed value for parity with the original analysis.",
            "lofMissingData": "LOF is not run when precipitation is missing; missing rainfall is not dry weather.",
            "lofFeatures": "Current precipitation and its 24-hour rolling mean, unscaled, matching the original method.",
            "coverage": {
                "expectedHours": int((end_ts - start_ts).total_seconds() / 3600),
                "weatherRows": len(weather),
                "temperatureObservedHours": int(temperature.notna().sum()),
                "precipitationObservedHours": int(precipitation.notna().sum()),
            },
            "sources": {"weather": _frame_metadata(weather)},
        },
    }
