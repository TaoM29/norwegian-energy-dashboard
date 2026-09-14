from __future__ import annotations

import pandas as pd

from app_core.loaders.elhub_span import load_energy_span_df


def _as_utc(value: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def matched_ytd_windows(year: int, end: pd.Timestamp) -> dict[str, pd.Timestamp]:
    """Return current/prior UTC YTD windows with the same calendar cutoff.

    The UI supplies ``end`` as an exclusive boundary. If that boundary falls
    inside February 29, the unmatched partial leap day is excluded. Callers also
    remove February 29 records from either window before comparing totals.
    """
    year = int(year)
    current_end = _as_utc(end)
    current_start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    next_year = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    current_end = min(max(current_end, current_start), next_year)
    try:
        prior_end = current_end.replace(year=current_end.year - 1)
    except ValueError:
        # There is no prior-year February 29. Compare through the last complete
        # matching calendar day and discard the current partial leap day.
        current_end = pd.Timestamp(year=year, month=2, day=29, tz="UTC")
        prior_end = pd.Timestamp(year=year - 1, month=3, day=1, tz="UTC")
    return {
        "current_start": current_start,
        "current_end": current_end,
        "prior_start": pd.Timestamp(year=year - 1, month=1, day=1, tz="UTC"),
        "prior_end": prior_end,
    }


def filter_matched_ytd(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    time_col: str = "timestamp",
) -> pd.DataFrame:
    """Apply a half-open YTD window and exclude the unmatched leap day."""
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    timestamps = pd.to_datetime(result[time_col], utc=True, errors="coerce")
    keep = (timestamps >= _as_utc(start)) & (timestamps < _as_utc(end))
    keep &= ~((timestamps.dt.month == 2) & (timestamps.dt.day == 29))
    result[time_col] = timestamps
    return result.loc[keep].copy()


def matched_ytd_expected_hours(start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Count comparable UTC hours in a half-open window, excluding February 29."""
    hours = pd.date_range(_as_utc(start), _as_utc(end), freq="h", inclusive="left")
    return int((~((hours.month == 2) & (hours.day == 29))).sum())


def matched_ytd_summary(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    *,
    windows: dict[str, pd.Timestamp],
    groups: list[str],
) -> pd.DataFrame:
    """Summarize comparable YTD totals and expose incomplete comparisons."""
    current_matched = filter_matched_ytd(
        current, start=windows["current_start"], end=windows["current_end"],
    )
    prior_matched = filter_matched_ytd(
        prior, start=windows["prior_start"], end=windows["prior_end"],
    )
    expected_current = matched_ytd_expected_hours(windows["current_start"], windows["current_end"])
    expected_prior = matched_ytd_expected_hours(windows["prior_start"], windows["prior_end"])
    if expected_current != expected_prior:
        raise ValueError("matched YTD windows do not contain the same number of UTC hours")

    def aggregate(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["group", f"{prefix}_kwh", f"{prefix}_hours"])
        frame = frame.dropna(subset=["value"])
        return (frame.groupby("group", as_index=False)
                .agg(**{f"{prefix}_kwh": ("value", lambda values: values.sum(min_count=1)),
                        f"{prefix}_hours": ("timestamp", "nunique")}))

    result = pd.DataFrame({"group": groups})
    result = result.merge(aggregate(current_matched, "current"), on="group", how="left")
    result = result.merge(aggregate(prior_matched, "prior"), on="group", how="left")
    result[["current_hours", "prior_hours"]] = result[["current_hours", "prior_hours"]].fillna(0).astype(int)
    result["expected_hours"] = expected_current
    result["is_comparable"] = (
        (result["current_hours"] == expected_current)
        & (result["prior_hours"] == expected_current)
        & result["current_kwh"].notna()
        & result["prior_kwh"].notna()
    )
    result["change_pct"] = (
        (result["current_kwh"] - result["prior_kwh"]) / result["prior_kwh"] * 100
    ).where(result["is_comparable"] & result["prior_kwh"].ne(0))
    return result


def load_energy_series_hourly(
    area: str,
    kind: str,
    group: str,
    year: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Load an hourly energy series for the UTC half-open interval ``[start, end)``.

    ``year`` remains in the public signature for existing page callers. Storage
    routing is now handled by the normalized loader, including spans that cross a
    legacy collection boundary. Empty hourly bins remain missing rather than
    becoming synthetic zero consumption or production.
    """
    if kind not in {"Production", "Consumption"}:
        raise ValueError("kind must be 'Production' or 'Consumption'")
    start_utc = _as_utc(start)
    end_utc = _as_utc(end)
    if start_utc >= end_utc:
        return pd.Series(dtype="float64")

    frame = load_energy_span_df(
        db=None,
        area=area,
        kind=kind,
        group=group,
        start=start_utc.to_pydatetime(),
        end=end_utc.to_pydatetime(),
    )
    if frame.empty:
        return pd.Series(dtype="float64")
    values = pd.to_numeric(frame["quantity_kwh"], errors="coerce")
    index = pd.DatetimeIndex(pd.to_datetime(frame["time"], utc=True))
    series = pd.Series(values.to_numpy(), index=index, dtype="float64")
    return series.sort_index().resample("h").sum(min_count=1)
