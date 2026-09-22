"""Frozen known-label controls for retrospective demand anomaly scoring."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from app_core.analysis.demand_anomalies import DemandAnomalyConfig, analyze_area
from app_core.analysis.forecast_evaluation import _norwegian_holidays
from scripts.run_forecast_reliability import write_new_json


def _ar1(rng, count, rho, sigma):
    values = np.empty(count)
    values[0] = rng.normal(0, sigma)
    innovations = rng.normal(0, sigma * np.sqrt(1 - rho * rho), count - 1)
    for position, innovation in enumerate(innovations, 1):
        values[position] = rho * values[position - 1] + innovation
    return values


def control_frame(seed: int, config: DemandAnomalyConfig) -> pd.DataFrame:
    index = pd.date_range(config.start, config.end, freq="h", inclusive="left", tz="UTC")
    local = index.tz_convert("Europe/Oslo")
    rng = np.random.default_rng(seed)
    elapsed = (index - index[0]).total_seconds().to_numpy() / 86400
    hour = np.asarray(local.hour)
    phase = (np.asarray(local.dayofyear) - 1 + hour / 24) / np.where(local.is_leap_year, 366, 365)
    holidays = set().union(*(_norwegian_holidays(year) for year in set(local.year)))
    holiday = np.array([date in holidays for date in local.date])
    temperature = 8 + 12 * np.sin(2 * np.pi * elapsed / 365.2425) + 2 * np.cos(2 * np.pi * hour / 24)
    temperature += _ar1(rng, len(index), .95, 3)
    mean = (1200 + 120 * np.sin(2 * np.pi * hour / 24) - 100 * (local.dayofweek >= 5)
            - 80 * holiday + 60 * np.sin(2 * np.pi * phase) + 20 * elapsed / 365.2425 - 20 * temperature)
    demand = mean + _ar1(rng, len(index), .8, 30)
    if np.min(demand) <= 0:
        raise ValueError("The frozen no-event generator must have positive demand")
    return pd.DataFrame({"demand": demand, "temperature": temperature}, index=index).rename_axis("time")


def inject(frame: pd.DataFrame, specification: dict) -> tuple[pd.DataFrame, list[dict]]:
    changed = frame.copy()
    events = []
    for month in specification["months"]:
        for event in specification["events"]:
            start = pd.Timestamp(year=2025, month=month, day=event["day"], hour=event["hourUTC"], tz="UTC")
            end = start + pd.Timedelta(hours=event["durationHours"])
            mask = (frame.index >= start) & (frame.index < end)
            amplitude = None
            if event["type"] == "observed_zero":
                changed.loc[mask, "demand"] = 0
            else:
                multiple = event.get("sigmaMultiple", event.get("sigmaMultipleByMonth", {}).get(str(month)))
                amplitude = multiple * specification["noise"]["marginalSigmaKWh"]
                changed.loc[mask, "demand"] += amplitude
            events.append({"type": event["type"], "start": start.isoformat(), "endExclusive": end.isoformat(),
                           "hours": int(mask.sum()), "amplitudeKWh": amplitude})
    return changed, events


def run_controls(directory: Path, config: DemandAnomalyConfig, specification: dict) -> dict:
    directory.mkdir(exist_ok=False)
    config = replace(config, peer_limit=specification["peerLimit"])
    summaries = []
    for seed in specification["seeds"]:
        print(f"Controlled validation seed {seed}", flush=True)
        frame = control_frame(seed, config)
        input_path = directory / f"{seed}-inputs.csv"
        frame.to_csv(input_path)
        frame = pd.read_csv(input_path, float_precision="round_trip", index_col="time", parse_dates=["time"])
        clean = analyze_area(frame, "NO1", config)
        changed, events = inject(frame, specification)
        injected = analyze_area(changed, "NO1", config)
        missing = frame.copy()
        missing_start = pd.Timestamp(specification["missingWindow"]["start"])
        missing_end = missing_start + pd.Timedelta(hours=specification["missingWindow"]["hours"])
        missing.loc[(missing.index >= missing_start) & (missing.index < missing_end), "demand"] = np.nan
        absent = analyze_area(missing, "NO1", config)
        for other in (injected, absent):
            for key in ("selection", "calibration", "metadata"):
                if other[key] != clean[key]:
                    raise AssertionError("Evaluation modifications changed frozen fitting or calibration")
        missing_rows = [row for row in absent["rows"] if missing_start <= pd.Timestamp(row["time"]) < missing_end]
        if len(missing_rows) != specification["missingWindow"]["hours"] or any(
            row["flagged"] or row["score"] is not None or row["status"] != "missing_demand" for row in missing_rows
        ):
            raise AssertionError("Missing demand must remain a coverage issue")
        rows = injected["rows"]
        clean_by_time = {row["time"]: row for row in clean["rows"]}
        affected_times = set()
        for event in events:
            affected = [row for row in rows if pd.Timestamp(event["start"]) <= pd.Timestamp(row["time"]) < pd.Timestamp(event["endExclusive"])]
            affected_times.update(row["time"] for row in affected)
            event.update(detected=any(row["flagged"] for row in affected),
                         flaggedHours=sum(row["flagged"] for row in affected),
                         scoredHours=sum(row["status"] == "ok" for row in affected),
                         cleanFlaggedHours=sum(clean_by_time[row["time"]]["flagged"] for row in affected),
                         newFlaggedHours=sum(row["flagged"] and not clean_by_time[row["time"]]["flagged"] for row in affected))
        outside = [row for row in rows if row["time"] not in affected_times]
        clean_outside = [row for row in clean["rows"] if row["time"] not in affected_times]
        if any(a != b for a, b in zip(outside, clean_outside)):
            raise AssertionError("Injected values changed unrelated hourly scores")
        summary = {
            "seed": seed, "cleanControl": {**clean["summary"], "falseFlagHours": clean["summary"]["flaggedHours"],
                                            "falseEpisodes": clean["summary"]["episodes"]},
            "events": events, "injectedOutsideEvents": {
                "hours": len(outside), "scoredHours": sum(row["status"] == "ok" for row in outside),
                "flaggedHours": sum(row["flagged"] for row in outside)},
            "missingHoursUnscored": len(missing_rows),
        }
        write_new_json(directory / f"{seed}-results.json", {"summary": summary, "clean": clean, "injected": injected,
                                                            "missingCoverage": absent["coverage"], "missingRows": missing_rows})
        summaries.append(summary)
    by_type = []
    for event_type in sorted({event["type"] for seed in summaries for event in seed["events"]}):
        events = [event for seed in summaries for event in seed["events"] if event["type"] == event_type]
        hours = sum(event["hours"] for event in events)
        by_type.append({"type": event_type, "events": len(events), "detectedEvents": sum(event["detected"] for event in events),
                        "affectedHours": hours, "scoredHours": sum(event["scoredHours"] for event in events),
                        "flaggedHours": sum(event["flaggedHours"] for event in events),
                        "cleanFlaggedHours": sum(event["cleanFlaggedHours"] for event in events),
                        "newFlaggedHours": sum(event["newFlaggedHours"] for event in events),
                        "eventsWithNewFlags": sum(event["newFlaggedHours"] > 0 for event in events)})
    scored = sum(seed["cleanControl"]["scoredHours"] for seed in summaries)
    false = sum(seed["cleanControl"]["falseFlagHours"] for seed in summaries)
    return {"specification": specification, "seeds": summaries, "byType": by_type,
            "cleanControl": {"scoredHours": scored, "falseFlagHours": false, "falseFlagRate": false / scored,
                             "falseEpisodes": sum(seed["cleanControl"]["falseEpisodes"] for seed in summaries)},
            "interpretation": "Known no-event synthetic controls only. Real-data flags do not have established normal/fault labels."}
