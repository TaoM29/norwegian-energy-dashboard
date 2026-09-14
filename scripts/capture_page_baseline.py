"""Capture original page tables/charts and server-side AppTest timings.

Run from the repository root with .venv/bin/python. Use --check to compare
current page outputs to the saved reference without rewriting it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st
from streamlit.testing.v1 import AppTest
from threadpoolctl import threadpool_info

PAGES = {
    "weather-overview": ("10_Weather_Overview_Stats_and_Sparklines.py", 5, 1),
    "weather-explorer": ("11_Weather_Explorer_Multi_Series_and_Resampling.py", 1, 0),
    "stl-spectrogram": ("40_STL_Decomposition_and_Spectrogram.py", 5, 1),
    "spc-lof": ("41_SPC_and_LOF_Data_Quality.py", 2, 2),
}
WIDGETS = ("selectbox", "multiselect", "slider", "select_slider", "radio", "number_input", "toggle", "checkbox")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_output(at, chart_count, table_count):
    errors = [e.message for e in at.exception]
    assert not errors, errors
    assert not list(at.error), [e.value for e in at.error]
    charts = [json.loads(chart.proto.spec) for chart in at.get("plotly_chart")]
    tables = [json.loads(table.value.to_json(orient="split", date_format="iso", double_precision=15)) for table in at.dataframe]
    assert len(charts) == chart_count, (len(charts), chart_count)
    assert len(tables) == table_count, (len(tables), table_count)
    return {
        "titles": [e.value for e in at.title],
        "captions": [e.value for e in at.caption],
        "info": [e.value for e in at.info],
        "warnings": [e.value for e in at.warning],
        "controls": [
            {"type": kind, "label": e.label, "value": e.value}
            for kind in WIDGETS for e in getattr(at, kind)
        ],
        "charts": charts,
        "tables": tables,
    }


def canonical(output):
    return json.dumps(output, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def capture(output_dir, repeats, check):
    if not check:
        output_dir.mkdir(parents=True, exist_ok=True)
    timings = {}
    manifest = {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor(), "streamlit": st.__version__},
        "dependency_snapshot": "../requirements-py311-macos.txt",
        "method": "perf_counter around AppTest.run(); initial navigation-registration run excluded; per-page caches cleared before first sample, then unchanged-widget reruns without explicit clearing. Imports/OS filesystem caches may already be warm. Includes local CSV access on cache miss, analysis, chart creation and Streamlit element serialization; excludes process startup, browser rendering, network and external services. Five reruns are descriptive samples, not a reliable p95 estimate.",
        "reference_adapter": "scripts/baseline_streamlit.py (repository-relative)",
        "thread_environment": {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")},
        "inputs": {str(p.relative_to(ROOT)): sha256(p) for p in sorted((ROOT / "data").glob("*.csv"))},
        "sources": {str(p.relative_to(ROOT)): sha256(p) for p in [ROOT / "scripts/baseline_streamlit.py", ROOT / "scripts/capture_page_baseline.py", *(ROOT / "app_core").rglob("*.py"), *[ROOT / "pages" / v[0] for v in PAGES.values()]]},
        "cases": {},
    }
    for slug, (filename, chart_count, table_count) in PAGES.items():
        # First run registers the custom navigation paths before switching.
        at = AppTest.from_file(ROOT / "scripts/baseline_streamlit.py", default_timeout=60).run()
        assert not at.exception, [e.message for e in at.exception]
        at.switch_page("../pages/" + filename)
        st.cache_data.clear()
        st.cache_resource.clear()
        started = time.perf_counter()
        at.run()
        first_seconds = time.perf_counter() - started
        reference = page_output(at, chart_count, table_count)
        encoded = canonical(reference)
        snapshot_path = output_dir / (slug + ".json.gz")
        if check:
            assert gzip.decompress(snapshot_path.read_bytes()) == encoded, f"Page output changed: {slug}"
            print(f"PASS {slug}: original page charts/tables/controls match saved reference", flush=True)
        else:
            samples = []
            for _ in range(repeats):
                started = time.perf_counter()
                at.run()
                samples.append(time.perf_counter() - started)
                assert canonical(page_output(at, chart_count, table_count)) == encoded, f"Nondeterministic page output: {slug}"
            snapshot_path.write_bytes(gzip.compress(encoded, mtime=0))
            timings[slug] = {
                "first_after_cache_clear_seconds": first_seconds,
                "unchanged_rerun_seconds": samples,
                "rerun_median_seconds": statistics.median(samples),
                "rerun_min_seconds": min(samples), "rerun_max_seconds": max(samples),
            }
            manifest["cases"][slug] = {
                "page": "pages/" + filename, "controls": reference["controls"],
                "scope": "NO1 production/solar, UTC 2021; 8759 available hours" if slug == "stl-spectrogram" else "Recorded weather, location unknown, 2020-01-01 to 2020-12-30; 8760 hours; inherited unit labels unverified",
                "chart_count": chart_count, "table_count": table_count,
                "snapshot": snapshot_path.name, "uncompressed_sha256": hashlib.sha256(encoded).hexdigest(),
                "reruns_identical": repeats,
            }
            print(f"{slug}: first {first_seconds:.3f}s; unchanged rerun median {statistics.median(samples):.3f}s; {repeats} identical reruns", flush=True)
        if slug == "weather-explorer":
            # Exercise a real control transition, keeping all other controls fixed.
            alternate_path = output_dir / "weather-explorer-daily.json.gz"
            alternate = None
            samples = []
            for _ in range(1 if check else repeats):
                next(e for e in at.selectbox if e.label == "Resample").select("Hourly")
                at.run()
                assert canonical(page_output(at, chart_count, table_count)) == encoded
                next(e for e in at.selectbox if e.label == "Resample").select("Daily")
                started = time.perf_counter()
                at.run()
                samples.append(time.perf_counter() - started)
                daily_output = page_output(at, chart_count, table_count)
                current = canonical(daily_output)
                assert current != encoded, "Resampling did not change the page output"
                if alternate is not None:
                    assert current == alternate, "Daily output changed between control transitions"
                alternate = current
            if check:
                assert gzip.decompress(alternate_path.read_bytes()) == alternate, "Daily page output changed"
                print("PASS weather-explorer-daily: real Hourly → Daily control transition matches reference", flush=True)
            else:
                alternate_path.write_bytes(gzip.compress(alternate, mtime=0))
                manifest["cases"]["weather-explorer-daily"] = {
                    **manifest["cases"][slug], "controls": daily_output["controls"],
                    "snapshot": alternate_path.name,
                    "uncompressed_sha256": hashlib.sha256(alternate).hexdigest(),
                    "interaction": "Resample: Hourly → Daily; all other controls unchanged",
                }
                timings["weather-explorer-daily"] = {
                    "hourly_to_daily_seconds": samples,
                    "transition_median_seconds": statistics.median(samples),
                }
                print(f"weather-explorer-daily: control transition median {statistics.median(samples):.3f}s; {repeats} identical outputs", flush=True)
    if not check:
        manifest["threadpools_after_capture"] = threadpool_info()
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        (output_dir / "timings.json").write_text(json.dumps(timings, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/baseline/pages")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.repeats < 5 and not args.check:
        parser.error("Use at least five repeat samples.")
    capture(args.output, args.repeats, args.check)
