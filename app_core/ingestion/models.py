from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import math
from typing import Any, Mapping, Optional


AREAS = ("NO1", "NO2", "NO3", "NO4", "NO5")
BASE_GROUPS = {
    "production": ("hydro", "other", "solar", "thermal", "wind"),
    "consumption": ("cabin", "household", "primary", "secondary", "tertiary"),
}
KNOWN_GROUPS = {
    "production": frozenset((*BASE_GROUPS["production"], "nuclear", "*")),
    "consumption": frozenset(
        (*BASE_GROUPS["consumption"], "industry", "private", "business", "*")
    ),
}
DATASETS = {
    "production": ("PRODUCTION_PER_GROUP_MBA_HOUR", "productionPerGroupMbaHour"),
    "consumption": ("CONSUMPTION_PER_GROUP_MBA_HOUR", "consumptionPerGroupMbaHour"),
}
SOURCE = "Elhub Energy Data API"
UNIT = "kWh"


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class EnergyObservation:
    timestamp: str
    area: str
    kind: str
    group: str
    value: Optional[float]
    unit: str
    source: str
    retrieved_at: str
    revision: Optional[str]
    quality: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def observation_from_record(
    record: Mapping[str, Any], kind: str, retrieved_at: datetime
) -> EnergyObservation:
    if kind not in DATASETS:
        raise ValueError(f"unsupported energy kind: {kind}")

    area = str(record.get("priceArea", "")).upper()
    group_field = f"{kind}Group"
    group = str(record.get(group_field, "")).lower()
    if area not in AREAS:
        raise ValueError(f"unexpected price area: {area or '<missing>'}")
    if not group:
        raise ValueError(f"missing {group_field}")
    if group not in KNOWN_GROUPS[kind]:
        raise ValueError(f"unexpected {kind} group: {group}")

    timestamp = parse_timestamp(record.get("startTime"), "startTime")
    end_timestamp = parse_timestamp(record.get("endTime"), "endTime")
    if (end_timestamp - timestamp).total_seconds() != 3600:
        raise ValueError(f"interval is not one hour for {area}/{kind}/{group}")
    raw_value = record.get("quantityKwh")
    value = None if raw_value is None else float(raw_value)
    if value is not None and (not math.isfinite(value) or value < 0):
        raise ValueError(f"invalid quantity for {area}/{kind}/{group} at {utc_iso(timestamp)}")

    revision_raw = record.get("lastUpdatedTime")
    revision = (
        utc_iso(parse_timestamp(revision_raw, "lastUpdatedTime"))
        if revision_raw is not None
        else None
    )
    quality = "missing" if value is None else "ok"
    if group == "*":
        quality = "aggregate_or_suppressed"
    elif kind == "consumption" and group in {"industry", "private", "business"}:
        quality = "aggregate"

    return EnergyObservation(
        timestamp=utc_iso(timestamp),
        area=area,
        kind=kind,
        group=group,
        value=value,
        unit=UNIT,
        source=SOURCE,
        retrieved_at=utc_iso(retrieved_at),
        revision=revision,
        quality=quality,
    )


def validate_local_dates(start: date, end: date) -> None:
    if end <= start:
        raise ValueError("end date must be after start date")
