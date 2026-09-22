# Step 3 — Visual forecast-error explorer

Implemented on 2026-09-22. This step exposes existing saved evaluation results;
it does not fit models, change experimental settings or overwrite artifacts.
See the [statistical roadmap](STATISTICAL_ANALYSIS_ROADMAP.md) and
[Step 2 evidence](STEP2_VALIDATION.md).

## What the page shows

The Forecasts page has a **Forecast error explorer**, below the saved forecast
chart, with four views:

- **Price areas:** an area-by-model heatmap of saved MAE minus seasonal-baseline
  MAE. Signed numbers and support counts supplement color. Negative means the
  model has lower error; positive means the baseline has lower error.
- **Seasons:** saved seasonal comparisons and their hourly, area-origin and
  distinct-origin-date support. These are descriptive; the original Phase 4
  artifact has only one evaluation date in each season.
- **Peak periods:** saved comparisons for peak and other hours, using the
  artifact's Europe/Oslo target-time classifications. The existing benchmark
  defines peak hours as weekdays 07:00–09:59 and 16:00–19:59 local time.
- **Forecast horizon:** MAE curves including the seasonal baseline, or measured
  interval-coverage curves with a separately labeled nominal reference. The
  underlying values and sample counts are available in a table.

All views describe the complete saved matched cohort. Area, date, model and
origin controls on the single-forecast chart do not recalculate these aggregates.
The explorer does not infer area-by-season or area-by-horizon intersections that
were not saved. It is available for evaluation artifacts; custom SARIMAX runs
retain their existing presentation.

Expected area/model and model/horizon combinations without a saved metric remain
unavailable. Charts leave gaps, tables label missing values, and exports use null
values with `savedMetric: false`. Missing observations are never converted to zero.

## Drill-down and state

Selecting a non-baseline heatmap cell opens a saved forecast for that area/model.
The example is selected by the largest origin-level mean of
`abs(actual - prediction) - abs(actual - baseline)`, breaking ties by ascending
saved origin timestamp. It is a baseline-relative MAE difference in kWh, not a
percentage error. The selected example is deliberately an extreme case and is
not presented as typical performance. Baseline cells are reference values and do
not choose an arbitrary zero-difference example.

Drill-down updates area, model plus baseline, origin, evaluation cohort and the
full saved target-date range together. It moves keyboard focus to the forecast
chart. This prevents an old chart date filter from hiding the selected example.
`explorer` and `explorerMeasure` URL parameters preserve the chosen breakdown and
horizon measure, including reload and browser history navigation. Invalid values
fall back to the area/error view.

CSV and JSON exports use the selected view's displayed metric rows and support;
JSON also identifies the result, cohort and selected horizon measure. Horizon
charts have a PNG export with result identity and matched-cohort context.

## Analytical checks

- Both historical and Step 2 artifacts provide 140 breakdown rows each: 20 area,
  16 season, 96 horizon and 8 peak-period rows. All **280 rows** were independently
  reconciled against saved predictions for observation count, signed paired MAE
  difference and inclusive interval coverage. No mismatch was found.
- Existing saved metric values are displayed directly. Where an older metric lacks
  `maeDeltaVsBaseline`, the fallback is its saved `mae - baselineMae`.
- Older Phase 4 support counts are derived from matching saved prediction rows.
  Its `origins` field counts distinct timestamps, so it is not mislabeled as the
  number of area-origins. If neither saved support nor predictions exist, support
  is unavailable.
- The exclusion disclosure separates failed evaluation origins from calibration
  failures, which remain in the complete artifact. The original study has one
  excluded evaluation area-origin; Step 2 has six.
- Exploratory labels follow the saved protocol's evidence status. This step adds
  no new statistical conclusions or uncertainty claims.

Artifact SHA-256 values remain unchanged:

| Artifact | SHA-256 |
| --- | --- |
| `phase4-household-24h` | `ae5a0fc4c144dfb208a2299ecd7f06adec46ce7d6b659f03cb8b0859b710c75e` |
| `step2-household-reliability-20260921` | `da08ba26d4d1c98ee98c0deb695d174b2365105f50eb9e31e4cf3c19c25c9b95` |

## Verification and publication

- All eight focused Forecasts browser tests passed. Three new tests use internally
  consistent synthetic predictions/metrics to check signed values, legacy counts,
  excluded areas, missing horizons, cohort isolation, exact drill-down, URL/history
  state, downloads and mobile keyboard scrolling. The horizon export test also
  passed after adding a labeled PNG download.
- TypeScript checking and the production Next.js build passed. No backend code
  changed, so no model-fitting or unrelated Python suite rerun was required.
- The observed Step 2 study was inspected at 1440×1000 and 390×844 in light and dark
  themes. Heatmap values, support, horizon curves and confined tooltips remained
  readable; page width stayed within 390 pixels on mobile. Wide tables scroll
  internally, and area row headers stay visible when the heatmap scrolls sideways.
- The original Phase 4 seasonal table was also checked in the browser: it
  correctly reports one origin date per season, with four or five area-origins.
- The PNG export was visually inspected; its title, legend and matched result
  identity are included. The horizon axis label was centered to avoid clipping.
- Documentation links and `git diff --check` passed. No dependency was added.

Code is local and uncommitted; no push or deployment is part of this step. The explorer uses existing artifacts, so
it does not require a new study or data-snapshot regeneration. A deployment must
still contain whichever saved results are intended to be visible.
