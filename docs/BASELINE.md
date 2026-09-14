# Phase 0 baseline

Recorded 2026-09-14 before application changes, at `70801b81f38348755602c4b3215c267ade176203`. The [control inventory](FEATURE_CONTROL_INVENTORY.md) records existing behavior and migration gaps.

## Repository provenance

Work is on `main`; the only remote is `origin`, pointing to `TaoM29/norwegian-energy-dashboard` for fetch and push. Application files match sanitized baseline `978d7c05a67f495302e6eaab2f8424ca77a2e233`. The inherited notebooks and input data are retained. Credential cleanup is documented in the README; do not restore pre-sanitization history.

## Test environment

**49 tests passed; no baseline failures.** The initial run took 49.16 seconds; a later warm run took 2.69 seconds. These are test-suite times, not application latency. Tests use synthetic data and mocked external services; they do not establish live data correctness or full page parity.

Environment: CPython 3.11.13, macOS 26.6.2, arm64. The [exact installed versions](baseline/requirements-py311-macos.txt) reproduce this environment, not a cross-platform lock. CI also declares Python 3.12 on Ubuntu; it was not run locally for this baseline.

From the repository root, using Python 3.11.13:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r docs/baseline/requirements-py311-macos.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
```

The MongoDB credential scan, including local history, passed. Credentials were not needed for baseline tests or captures.

## Representative observations

Original page calculations were exercised with the two tracked CSVs:

- `data/open-meteo-subset.csv`: 8,760 hourly rows, 2020-01-01 through 2020-12-30. Location/model/timezone and authoritative unit metadata are absent. Original pages label its naive timestamps UTC; this is inherited behavior, not verified provenance. SHA-256: `d2943315cc7a25711e8dfdfecb27834d237c3de1fd29d30a43b0153348075649`.
- `data/elhub_prod_by_group_hour_2021.csv`: 215,353 rows across areas/groups. The NO1 solar 2021 UTC slice has 8,759 hours, missing the final hour. January has 744 complete hours. SHA-256: `9038fe7981b1df9d5aa340b0f1aaf1d3ab5f2f05c866e4cd2ec7b819731eb611`.

Five page cases reproduced: Weather Overview, hourly/daily Weather Explorer, STL/spectrogram and SPC/LOF. With default page controls, recorded weather produced 56 SPC flags and 88 LOF flags; these are statistical flags, not verified faults. January solar STL/spectrogram, partial-season Snow Drift functions and a bounded three-fold real SARIMAX run also reproduced. Weather and energy were not joined because their recorded years differ.

| Page | First run after application-cache clear | Median of five unchanged reruns |
| --- | ---: | ---: |
| Weather Overview | 81 ms | 72 ms |
| Weather Explorer | 75 ms | 64 ms |
| Full-year STL & Spectrogram | 4,799 ms | 3,673 ms |
| SPC & LOF | 466 ms | 115 ms |

Hourly → Daily transitions had a 74 ms median. These measurements wrapped Streamlit `AppTest.run()`, including calculations and element serialization but excluding browser/network/database time. Imports and OS caches were warm; machine load was uncontrolled. They are descriptive samples, not p95 estimates or deployment targets.

## Historical capture evidence

Commit **`f15c95d`** retains the complete source/input hashes, parameters, numerical outputs, screenshots, timings and capture code. For example, `git show f15c95d:docs/REFERENCE_OUTPUTS.md` retrieves the original report. This preserves auditability without maintaining a second application runner, generated result collections or a benchmark framework in the working tree. The raw test log was redundant with this record and was removed too.

Phase 0 established a representative baseline, not exhaustive acceptance. Live coverage, DST, model/units, missing-data semantics and untested page paths remain work for Phase 1 and feature migration. Original datasets, notebooks, application features and correctness tests remain available.
