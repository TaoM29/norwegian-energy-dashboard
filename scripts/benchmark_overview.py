#!/usr/bin/env python3
"""Measure the retained Streamlit energy pages and the overview API.

Run from the repository root while the API is listening on 127.0.0.1:8000.
The script prints Markdown; redirect it only when intentionally refreshing the
checked-in performance record.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import hashlib
import http.client
import json
import logging
import math
import platform
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter
from typing import Callable, Iterator
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fastapi
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from app_core.ingestion.models import BASE_GROUPS
from app_core.loaders import mongo_utils
from app_core.loaders.mongo_utils import load_energy_records

DATABASE = ROOT / "data" / "energy.sqlite"
PAGES = {
    "Streamlit production": ROOT / "pages" / "12_Energy_Production.py",
    "Streamlit consumption": ROOT / "pages" / "13_Energy_Consumption.py",
}


def _milliseconds(action: Callable[[], object]) -> float:
    started = perf_counter()
    action()
    return (perf_counter() - started) * 1_000


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "median": statistics.median(values),
        "p95": _nearest_rank(values, 0.95),
        "min": min(values),
        "max": max(values),
    }


def _clear_streamlit_caches() -> None:
    st.cache_data.clear()
    st.cache_resource.clear()
    mongo_utils._snapshot_metadata.cache_clear()


def _new_page(path: Path, area: str, year: int) -> AppTest:
    app = AppTest.from_file(str(path), default_timeout=60)
    app.session_state["selected_area"] = area
    app.session_state["selected_year"] = year
    return app


def _assert_page(app: AppTest, area: str, year: int) -> None:
    if app.exception:
        raise RuntimeError(f"Streamlit page failed: {app.exception[0].message}")
    if not app.selectbox or not app.multiselect or len(app.get("plotly_chart")) != 2:
        raise RuntimeError("Streamlit page did not render its controls and two charts")
    expected = f"Scope: **{area}, {year}**"
    if not app.caption or expected not in app.caption[0].value:
        raise RuntimeError(f"Streamlit page did not retain the requested scope: {expected}")


def _streamlit_runs(
    path: Path, area: str, year: int, count: int
) -> tuple[float, list[float]]:
    _clear_streamlit_caches()
    app = _new_page(path, area, year)
    cold = _milliseconds(app.run)
    _assert_page(app, area, year)
    months = [7, 1]
    values = []
    for index in range(count):
        app.selectbox[0].select(months[index % len(months)])
        values.append(_milliseconds(app.run))
        _assert_page(app, area, year)
    return cold, values


@contextmanager
def _connection(api_url: str) -> Iterator[tuple[http.client.HTTPConnection, str]]:
    parsed = urlsplit(api_url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("--api-url must be an http URL")
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)
    try:
        yield connection, parsed.path.rstrip("/")
    finally:
        connection.close()


def _get_json(connection: http.client.HTTPConnection, path: str) -> dict:
    connection.request("GET", path, headers={"Accept": "application/json"})
    response = connection.getresponse()
    body = response.read()
    if response.status != 200:
        raise RuntimeError(f"GET {path} returned {response.status}: {body[:300]!r}")
    return json.loads(body)


def _overview_path(base_path: str, *, area: str, start: str, end: str) -> str:
    return f"{base_path}/api/overview?{urlencode({'area': area, 'start': start, 'end': end})}"


def _api_series(
    api_url: str, *, area: str, start: str, end: str, count: int
) -> tuple[float, list[float], dict]:
    with _connection(api_url) as (connection, base_path):
        path = _overview_path(base_path, area=area, start=start, end=end)
        result: dict = {}

        def first_request() -> None:
            nonlocal result
            result = _get_json(connection, path)

        first = _milliseconds(first_request)
        warm = [_milliseconds(lambda: _get_json(connection, path)) for _ in range(count)]
    return first, warm, result


def _coverage(api_url: str) -> dict:
    with _connection(api_url) as (connection, base_path):
        return _get_json(connection, f"{base_path}/api/coverage")


def _loader_totals(area: str, year: int) -> dict[str, float]:
    start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    frame = load_energy_records(start=start, end=end, areas=[area])
    totals = {}
    for kind, groups in BASE_GROUPS.items():
        selected = frame[(frame["kind"] == kind) & frame["group"].isin(groups)]
        totals[kind] = float(selected["value"].sum(min_count=1)) / 1_000.0
    return totals


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _row(name: str, boundary: str, values: list[float], *, percentile: bool = True) -> str:
    result = _summary(values)
    p95 = f"{result['p95']:.1f}" if percentile else "—"
    return (
        f"| {name} | {boundary} | {result['n']} | {result['median']:.1f} | "
        f"{p95} | {result['min']:.1f} | {result['max']:.1f} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--area", default="NO1", choices=("NO1", "NO2", "NO3", "NO4", "NO5"))
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if args.iterations < 20:
        parser.error("--iterations must be at least 20 for the recorded p95")
    if not DATABASE.is_file():
        parser.error(f"missing snapshot: {DATABASE}")

    logging.disable(logging.WARNING)

    year_start = date(args.year, 1, 1).isoformat()
    year_end = date(args.year + 1, 1, 1).isoformat()
    coverage = _coverage(args.api_url)
    default_start = coverage["suggestedRange"]["start"]
    default_end = coverage["suggestedRange"]["end"]

    streamlit_results = {}
    # Direct page-file AppTest lacks the multipage registry. Patching this one
    # navigation element lets the unchanged page execute; data and UI work remain real.
    with patch("streamlit.page_link", return_value=None):
        for label, path in PAGES.items():
            cold, warm = _streamlit_runs(
                path, args.area, args.year, args.iterations
            )
            streamlit_results[(label, "cold")] = [cold]
            streamlit_results[(label, "warm")] = warm

    matched_first, matched_warm, matched = _api_series(
        args.api_url,
        area=args.area,
        start=year_start,
        end=year_end,
        count=args.iterations,
    )
    default_first, default_warm, default = _api_series(
        args.api_url,
        area=args.area,
        start=default_start,
        end=default_end,
        count=args.iterations,
    )

    loader_totals = _loader_totals(args.area, args.year)
    for kind in ("production", "consumption"):
        api_total = matched["headline"][kind]["mwh"]
        if api_total is None or abs(loader_totals[kind] - float(api_total)) > 0.001:
            raise RuntimeError(
                f"matched {kind} total differs: page loader={loader_totals[kind]:.6f} MWh, "
                f"API={api_total!r} MWh"
            )

    print("# Overview server-side benchmark")
    print()
    print(
        f"Snapshot: `{_sha256(DATABASE)}` ({DATABASE.stat().st_size:,} bytes); "
        f"commit `{_git_head()}`."
    )
    print(
        "Measured source SHA-256: "
        f"backend `{_sha256(ROOT / 'backend' / 'main.py')}`; "
        f"production page `{_sha256(PAGES['Streamlit production'])}`; "
        f"consumption page `{_sha256(PAGES['Streamlit consumption'])}`."
    )
    print(
        f"Environment: Python {platform.python_version()}, Streamlit {st.__version__}, "
        f"FastAPI {fastapi.__version__}, {platform.platform()} ({platform.machine()})."
    )
    print()
    print("| Path | Measurement boundary | n | median ms | p95 ms | min ms | max ms |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for label, _path in PAGES.items():
        print(_row(
            label,
            "AppTest, cache clear (descriptive)",
            streamlit_results[(label, "cold")],
            percentile=False,
        ))
        print(_row(label, "AppTest, warm month filter", streamlit_results[(label, "warm")]))
    print(_row("API, matched calendar year", "HTTP loopback, warm", matched_warm))
    print(_row("API, suggested 28 days", "HTTP loopback, warm", default_warm))
    print()
    print(
        f"First measured API request: {matched_first:.1f} ms for {year_start}–{year_end}; "
        f"{default_first:.1f} ms for {default_start}–{default_end}."
    )
    print(
        f"Matched totals ({args.area}, UTC [{year_start}, {year_end})): "
        f"production {loader_totals['production']:.3f} MWh; "
        f"consumption {loader_totals['consumption']:.3f} MWh. "
        "The retained-page loader and API agree within 0.001 MWh."
    )
    print(
        f"The suggested API case spans {(date.fromisoformat(default_end) - date.fromisoformat(default_start)).days} "
        f"days ({default_start}–{default_end}) and is not a matched Streamlit comparison. "
        f"Its response contains {len(default['daily'])} daily rows."
    )


if __name__ == "__main__":
    main()
