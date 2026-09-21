# Phase 3 — Exploration and diagnostics parity

Phase 3 migrates the exploration and diagnostics workflows into Next.js and FastAPI. Streamlit remains runnable, including SARIMAX, pending Phase 4. This report records the local September 15, 2026 validation; it does not replace the historical Phase 0 captures or Phase 2 measurements.

Subsequent correction (2026-09-21): correlation now preserves missing hourly slots, and exploration wind-rose sectors are compass-centered. See the [Step 0 completion record](STATISTICAL_ANALYSIS_ROADMAP.md#step-0-completion-record--2026-09-21) for changed behavior and regression checks. The original validation below remains a historical record.

## Parity delivered

| Original experience | Replacement | Numerical verification |
| --- | --- | --- |
| Energy production / consumption | `/explore`: group selection, totals, hourly/daily/weekly sums, values table | Exact sums, missing values, coverage and group filters in `test_explore_api.py` |
| Weather overview / explorer | `/explore`: summaries, monthly patterns, 16-sector wind rose, variables, normalization, rolling window and opacity | Physical units, rainfall sums, circular direction averages, normalization and rolling regressions |
| Geographic energy map | `/regional`: real NO1–NO5 boundaries, area and coordinate selection, dates, kind/groups and regional means | Actual GeoJSON, record-weighted means, partial coverage and nuclear selection in `test_regional_api.py` |
| Snow drift | `/regional`: exact-coordinate weather, seasons, transport/fetch distance, relocation coefficient, fence type, seasonal/monthly/sector results and source preview | Transport threshold, units, direction boundaries, both Tabler branches, fence factors and partial seasons in `test_snow_drift.py` |
| Sliding correlation | `/diagnostics`: energy/weather selection, rolling window, lag, normalization and aligned series | Retained rolling Pearson helper and lag sign checked in `test_diagnostics_api.py` |
| STL and spectrogram | `/diagnostics`: seasonal period/smoothers, robust fitting, spectral window/overlap, four components and heatmap | Components and spectral values compared with retained analytical helpers; incomplete input rejection |
| SPC and LOF | `/diagnostics`: DCT fraction, sigma threshold, contamination and neighbors; scores, charts and candidate tables | Retained algorithms and candidate timestamps checked against full-resolution fixtures |

The shared navigation carries area and dates between views. Each workspace persists its controls in the URL; browser end dates are inclusive and API intervals are UTC `[start, end)`. Data CSV, metadata JSON and chart PNG downloads expose values, units, parameters, coverage and source provenance. Explore downloads contain every aggregated value; diagnostics downloads contain the displayed, explicitly sampled values plus candidate records and sampling metadata.

## Deliberate behavior changes

- Published, validated local snapshots replace page-time MongoDB reads and area-weather downloads. Snow drift still loads weather for the exact selected point. Area weather remains an explicitly labeled fixed-city proxy.
- Energy uses the disjoint base groups from the Phase 1 schema. Empty selections produce a helpful validation message instead of silently selecting everything. The map retains nuclear as a selectable production group, showing missing coverage when no observations exist.
- Regional means weight source observations equally instead of averaging collection-level means. With multiple groups selected, the label explicitly describes the mean per hourly group observation.
- Wind-direction aggregation and rolling means use circular vectors: 359° and 1° average to north, not south. Monthly rainfall is summed; temperature, wind speed and gusts use arithmetic means. Summary values retain physical units even when chart lines are normalized.
- STL and spectrogram reject internal missing hours instead of manufacturing zero observations. Correlation uses complete pairs. SPC retains the original documented interpolation/fill policy; LOF rejects missing precipitation. No statistical candidate is presented as a verified fault. The inherited LOF method can warn about duplicate rainfall feature values in dry periods; zero candidates do not establish that the data is error-free.
- Date windows replace separate year/month controls and make the exact view reproducible. The API bounds ordinary analysis to 366 days. Snow season requests are bounded to 25 seasons.

## Scientific assumptions

Snow-drift calculations preserve the original Tabler formulas: potential transport is `sum(u^3.8 × 3600) / 233847` in kg/m; snowfall uses the original temperature threshold and precipitation as snow water equivalent; transport and fetch distances are metres. Sixteen nearest compass sectors, seasonal July–June windows, the relocation coefficient, transport branches and fence factors are covered by fixtures. Partial seasons are labeled. Estimated fence heights remain indicative model outputs, not site-specific engineering recommendations.

The correlation, STL, spectrogram, DCT/SPC and LOF routines retain their original analytical meaning and expose effective parameters. Full observations feed the calculations before any display sampling. A normalized chart or an outlier score does not establish causality or data corruption.

## Summary precomputation and rendering

Snapshot publication builds indexed daily group summaries and daily base-group totals before atomic replacement. Null values stay missing and completeness counts require all base groups in the same hour. Updating observations invalidates summaries. Existing snapshots without summaries remain readable through the raw-query fallback. `test_backend_data.py` verifies equality before/after publication, coverage and invalidation.

The local snapshot produced 104,294 daily group rows and 20,830 daily total rows in 10.46 seconds. The overview reads these totals. Daily and weekly Explore views use group summaries when every selected day is complete, otherwise falling back to hourly observations. Numerical fixtures verify equivalent totals and coverage; summation order can produce last-bit floating-point differences around 1e-8 kWh. This does not alter source observations. Chart points and spectral grids are reduced only after analytical calculations, with counts and sampling policies displayed. The original hourly data and historical scientific evidence are retained.

## Verification

- Full Python suite: **144 passed**; two existing dependency deprecation warnings.
- Next.js production build and TypeScript checks passed.
- Real published-snapshot API smoke checks passed for exploration, regional summaries and all three diagnostics endpoints.
- NO1 2025 production in Explore remains **19,717,508.644 MWh**, matching the Phase 2 reference.

Browser checks used the production build on localhost. Explore energy/weather rendered at desktop and 390px widths; daily aggregation and URL reload restored the selected values. All three diagnostics methods ran on real observations, including the spectral heatmap and candidate tables. Regional selection rendered all five real boundaries; a polygon click selected NO2 and the exact clicked coordinates. Keyboard coordinates and full URL restoration also worked. Safari CSV and JSON downloads produced files; chart export produced a valid 1254×680 PNG. Regional map, metrics and snow charts also rendered at 390px without page overflow.

A live Bergen point calculation at `60.3913, 5.3221` for July 2024–June 2025 returned complete weather coverage, snowfall-controlled transport of approximately **44.7 t/m** and an indicative Wyoming fence height of **2.13 m**. Desktop charts, seasonal/monthly tables and the directional rose rendered. These values describe this selected ERA5 grid point and these model parameters.

Integration checks caught and corrected a missing-numeric-URL default, stale regional results during loading, mobile chart-label collisions and hidden partial-coverage information. No commits or pushes were made.

**Gate passed:** every Phase 3 parity row has a replacement UI, numerical checks and documented behavior changes. Phase 4 forecasting and trustworthy evaluation is next.
