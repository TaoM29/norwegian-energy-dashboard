# Phase 0 baseline

Captured on 2026-09-14 before changes to application code or existing tests. The control inventory is in [FEATURE_CONTROL_INVENTORY.md](FEATURE_CONTROL_INVENTORY.md). All replacement features remain pending.

## Repository provenance

- Starting checkout: `70801b81f38348755602c4b3215c267ade176203`, on `main`, with a clean working tree.
- The only remote is `origin`, with both fetch and push pointing to `git@github.com:TaoM29/norwegian-energy-dashboard.git`.
- The local checkout contains 152 commits reachable from the starting commit. The sanitized application baseline is `978d7c05a67f495302e6eaab2f8424ca77a2e233`; the original pre-sanitization source identifier is recorded in the implementation plan and must not be merged back in.
- Comparing the sanitized application baseline with the starting checkout shows no changes to `app.py`, `pages/`, `app_core/`, `requirements.txt`, or `data/`. The notebook connection cell was sanitized and credential-scanner tests were added.
- `.streamlit/secrets.toml` is ignored and untracked. The targeted MongoDB credential scan passed, including all local history. No credentials or live database access were needed for this baseline.

## Reproduce the Python environment

The baseline uses CPython **3.11.13**, **macOS 26.6.2**, **arm64**, in an isolated `.venv`. The machine's default `python` is 3.9.16, outside the project's CI matrix, so it was not used for the baseline. CI declares Python 3.11 and 3.12 on Ubuntu; this local run does not establish the result on Python 3.12 or Linux.

The initial environment was installed from the unchanged `requirements.txt`. All installed versions, including pip and setuptools, are captured in [baseline/requirements-py311-macos.txt](baseline/requirements-py311-macos.txt). This is a platform-specific version snapshot, not a hash-verified cross-platform lock or a claim that the latest dependencies preserve all page behavior. `pip check` reports no broken requirements.

From the repository root, with Python 3.11.13 available:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r docs/baseline/requirements-py311-macos.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_secrets.py --history
```

Use a fresh virtual environment when reproducing this snapshot. Package installation needs network access; the existing tests use fake collections, patched HTTP calls, temporary CSVs and synthetic series. The SARIMAX backtest test substitutes a dummy model, so its result does not validate real model fitting.

## Test result and regression boundary

**49 passed in 49.16 seconds; exit code 0.** There were no reported failures, errors, skips, expected failures or warnings. The [captured test output](baseline/pytest-py311-macos.txt) identifies the source revision and environment.

There are **no baseline test failures to carry forward** in this environment. Later failures against this source and dependency snapshot should be investigated as regressions; failures after dependency or platform changes need a separate compatibility comparison. No application functions, existing tests or dependency ranges were changed to achieve this result.

Coverage includes CSV parsing, mocked energy/weather loaders, collection selection, UTC conversion, aggregation, correlations, STL, spectrograms, SPC/LOF, z-scores, forecast helpers and credential detection. It does not cover the full Streamlit page interactions or every page-embedded calculation. The inventory identifies those gaps; passing tests are not evidence that they are already correct.

## Representative output capture — completed

The [reference output report](REFERENCE_OUTPUTS.md) now records original-page screenshots, complete charts/tables, numerical results, input/source hashes, controls, cache conditions and timing samples. Five page cases and seven measured numerical/data-loading operations reproduce; all 49 existing tests still pass. Phase 0 is complete for this representative recorded-input set. Unit-test and server-side execution times are not browser latency; live MongoDB/weather coverage, full browser journeys and exhaustive numerical parity remain unverified.
