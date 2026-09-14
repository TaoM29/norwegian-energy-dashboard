# Phase 0 — representative outputs and timings

Captured 2026-09-14 using the retained Streamlit pages and analysis functions, with the [Python 3.11 dependency snapshot](baseline/requirements-py311-macos.txt). **Phase 0 is complete for this recorded-input reference set.** No original application files or features were changed or removed. These artifacts establish reproducible comparison points; they do not establish live coverage, scientific correctness, full feature parity, or deployment performance.

## Inputs and scope

| Input | Recorded coverage and use | Limitation |
| --- | --- | --- |
| `data/elhub_prod_by_group_hour_2021.csv` | 215,353 rows across areas/groups. Numerical STL/spectrogram: NO1 solar, January 2021, 744 complete hourly rows. Forecast: NO1 solar, January–June 2021, 181 complete daily totals. Original STL page: NO1 solar, the 2021 UTC slice, 8,759 hours. | The raw file begins at 2020-12-31 23:00 UTC and ends at 2021-12-31 22:00 UTC. The page's UTC-year selection excludes the first raw hour and lacks the final hour of 2021; it is not a complete UTC year. |
| `data/open-meteo-subset.csv` | 8,760 hourly rows from 2020-01-01 00:00 through 2020-12-30 23:00. Used unchanged by weather pages, SPC, LOF and Snow Drift functions. | Location, model, authoritative units and timezone metadata are absent. Original clock strings are parsed with `utc=True` to reproduce the page, not to certify UTC identity. 2020 is a leap year: December 31 is absent. Both July–June snow seasons are partial. |

Input SHA-256 hashes, row counts, selections, missingness, source hashes and parameters are recorded in [analysis/summary.json](baseline/analysis/summary.json) and [pages/manifest.json](baseline/pages/manifest.json). The two files cover different years and are **not joined, relabeled, or shifted to create a weather/energy forecast experiment**.

## Original page captures

The [reference harness](../scripts/baseline_streamlit.py) runs the existing page files with their original calculations, controls and charts. Only external data access is replaced with the tracked CSVs. It patches the weather/year loader entry points and MongoDB factory while the page runs, blocks Requests network access, fixes the sample scope, and adds a visible recorded-data banner. It registers a subset of navigation pages and adjusts page-link paths because the runner lives in `scripts/`. Links to uncaptured pages from Home are displayed as text. This is a capture tool, not a new public fixture mode or a replacement navigation design.

| Case | Selection and controls | Preserved output |
| --- | --- | --- |
| Weather Overview | Recorded 2020 weather; no local controls | Summary table with all five sparklines, four monthly charts, 16-sector wind rose |
| Weather Explorer — Hourly | All five variables; all available months; normalization on; 24-hour rolling mean; opacity 0.9 | Complete five-series chart and controls |
| Weather Explorer — Daily | Same controls, changing only Resample from Hourly to Daily | Complete resampled chart; five repeated Hourly → Daily transitions |
| STL & Spectrogram | NO1 solar, available 2021 UTC rows; period 24, seasonal 13, trend 365, robust on; spectral window 168, overlap 84 | Source preview, four component charts, complete spectral heatmap |
| SPC & LOF | Recorded weather; DCT fraction 0.01, width 3; contamination 0.01, neighbors 60 | Two charts and two sample tables; 56 SPC flags and 88 LOF flags |

The five [compressed page snapshots](baseline/pages/manifest.json) retain complete Plotly specifications, dataframe contents, control values and displayed status text. They can be read with Python `gzip` and `json`; chart arrays retain Plotly's typed-array representation. Each case reproduced exactly over five reruns/transitions and again in a fresh capture-check process. Snapshots are deliberately exact for this pinned environment; review intentional numerical, dependency or presentation changes rather than silently overwriting them.

### Screenshots and browser checks

Screenshots were inspected in the Codex in-app browser at its default **1280 × 720 CSS-pixel viewport**, device pixel ratio 2, inherited dark theme, without network/device emulation. See [browser conditions](baseline/screenshots/browser.json). These are viewport section captures, not full-page screenshots or a responsive-design acceptance test.

- Weather: [summary and sparklines](baseline/screenshots/weather-overview.jpg), [monthly charts](baseline/screenshots/weather-monthly.jpg), [wind rose](baseline/screenshots/weather-wind-rose.jpg).
- Explorer: [hourly](baseline/screenshots/weather-explorer.jpg) and [daily](baseline/screenshots/weather-explorer-daily.jpg); the Daily selection and resulting chart were verified in the browser.
- Energy diagnostics: [parameters and source preview](baseline/screenshots/stl-parameters.jpg), [observed and seasonal components](baseline/screenshots/stl-components.jpg), [spectrogram tab](baseline/screenshots/spectrogram.jpg).
- Data quality: [temperature SPC](baseline/screenshots/spc-temperature.jpg) and [precipitation LOF](baseline/screenshots/lof-precipitation.jpg); both tabs were opened and the displayed flag counts checked.

Runtime inspection corrected the source-only inventory: dataframe toolbars provide **CSV downloads**, and Plotly toolbars provide **PNG downloads**. No custom provenance-aware export exists. Download contents were not tested. Existing layout defects are preserved as evidence: some STL/spectrogram axis labels are clipped, and the wind rose has low-contrast labels in this dark theme. The source's ERA5/unit/full-year wording is also retained below the harness's explicit provenance warning.

## Numerical references

The [numerical capture script](../scripts/capture_analysis_baseline.py) calls the existing analysis functions. Snow Drift definitions are extracted unchanged from the page using Python's syntax tree, so no duplicate implementation of its transport formulas was introduced. [Numerical artifact guidance](baseline/analysis/README.md) explains each CSV/NPZ and its parameters.

- January solar STL retains observed, trend, seasonal and residual values; the spectrogram retains all 85 × 7 magnitudes, both frequency units and an exact nanosecond timestamp axis.
- SPC/LOF retain every input, score, bound and flag, rather than only the summary counts. The inherited LOF warning about duplicate feature values is recorded; a flag is not evidence of a verified fault.
- Snow Drift retains partial-season totals and the average 16-sector transport. These are formula regression references with unverified input units, not estimates of site conditions.
- Forecasting uses real statsmodels SARIMAX `(1,0,0)(1,0,0,7)` without weather and a seasonal-naive lag of seven days. Three matched seven-day folds retain their cutoffs, actuals, forecasts and MAE/RMSE/MASE. Per-fold metrics reconcile with the unchanged helper's summary. This is a bounded execution reference, not a tuned model, untouched holdout or operational benchmark.

Five repeated executions agreed with the first result at `rtol=atol=1e-10`, with exact schemas/time axes and zero observed numerical difference. A separate process reproduced all deterministic CSV, NPZ and summary files byte for byte. Timings and environment records are separate from deterministic output hashes.

## Timings

Page measurements wrap `AppTest.run()` with a monotonic timer. They include local CSV access on cache misses, calculations, figure creation and Streamlit element serialization. Navigation registration is run before measurement; page caches are then cleared for the first sample. Imports and the OS filesystem cache may already be warm. The next five samples leave widgets and caches unchanged. These are **server-side page execution measurements**, excluding process startup, browser painting, network and database/API latency. Five samples are descriptive, not a reliable p95 estimate.

| Original page | First run after cache clear | Median of five unchanged reruns | Rerun range |
| --- | ---: | ---: | ---: |
| Weather Overview | 81 ms | 72 ms | 71–95 ms |
| Weather Explorer | 75 ms | 64 ms | 63–100 ms |
| STL & Spectrogram | 4,799 ms | 3,673 ms | 3,659–3,739 ms |
| SPC & LOF | 466 ms | 115 ms | 112–168 ms |

Five Hourly → Daily weather-control transitions had a median server-side execution time of **74 ms** (73–76 ms). Raw samples are in [pages/timings.json](baseline/pages/timings.json); environment, source and thread details are in its manifest. Full-year STL recomputes on rerun and is the clear slow case in this set.

Separate [numerical timing samples](baseline/analysis/timings.csv) measure first and five repeated helper calls with one requested BLAS/OpenMP thread; [analysis/environment.json](baseline/analysis/environment.json) states the exact boundaries. Page timings use the recorded default thread configuration. These were measured sequentially without another baseline benchmark running. Other machine load was not controlled, and the OS cache was not flushed. Do not compare the short January numerical STL case directly with the full-year page case, or these local timings with Phase 2 browser latency targets.

## Reproduce and compare

Set up the [baseline environment](BASELINE.md#reproduce-the-python-environment), then run from the repository root:

```bash
# Compare current original-page outputs to the saved reference (does not rewrite it).
.venv/bin/python scripts/capture_page_baseline.py --check

# Capture fresh numerical outputs and timings outside the saved reference.
.venv/bin/python scripts/capture_analysis_baseline.py --output /tmp/energy-analysis-comparison

# Capture fresh page outputs and timings outside the saved reference.
.venv/bin/python scripts/capture_page_baseline.py --output /tmp/energy-page-comparison

# Open the original pages against recorded inputs for visual comparison.
.venv/bin/python -m streamlit run scripts/baseline_streamlit.py \
  --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

Compare numerical arrays with the recorded tolerance, checking schema and timestamp axes exactly; compare input/source hashes before interpreting differences. The saved snapshot commands without `--output` intentionally regenerate references and should only be used when updating the baseline is intended. Screenshot recapture requires browser navigation to the documented sections; the scripts capture data/charts, not screenshots.

Validation on completion: the existing suite still reports **49 passed**; all five page comparisons pass in a fresh process, capture scripts compile, deterministic numerical artifacts reproduce, and artifact hashes/document links are checked. No live credentials are needed.

## Limits carried into later phases

Phase 0 requires representative references, not exhaustive runtime coverage. Consumption, annual-production total branches, live geography/map clicks, paired energy/weather correlations, full Snow Drift page interaction, forecast-page interaction, exogenous forecasts, empty/error states and full mobile/keyboard journeys are not covered by these captures. Capture additional cases before migrating those features. Data correctness, DST, authoritative units/model identity, current coverage and source freshness remain Phase 1 work; replacement feature parity and browser latency remain later acceptance gates. The retained application remains runnable through `streamlit run app.py` with its existing configuration requirements.
