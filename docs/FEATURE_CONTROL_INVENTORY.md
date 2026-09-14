# Streamlit feature and control inventory

Prepared 2026-09-14 for Phase 0. This is a historical inventory of the retained Streamlit application at the Phase 0 baseline. Phase 1 changes to data loading, dates and missingness are described in [the data pipeline](DATA_PIPELINE.md). It supplements the higher-level feature map in `docs/IMPLEMENTATION_PLAN.md`; it does not claim that the listed outputs were produced successfully against live MongoDB or Open-Meteo data.

All replacement work is **migration pending**. The Streamlit application remains the reference implementation until each replacement passes the acceptance checks in the implementation plan.

## Verification status and boundaries

- **Statically inspected:** `app.py`, every file in `pages/`, the page-facing helpers in `app_core/analysis/` and `app_core/loaders/`, and the current tests in `tests/`.
- **Runtime evidence:** the [baseline record](BASELINE.md) summarizes representative page/numerical checks and points to the complete historical captures in Git. These checks do not establish live data correctness or full feature parity.
- **External contracts:** collection contents, current Open-Meteo response units/model identity, full-year completeness, live map interaction, model convergence, and page timings remain unverified here.
- **Credentials:** MongoDB access is server-side through `st.secrets["MONGO_URI"]`, with database name defaulting to `ind320`. No credential value is recorded here. Sources: `app_core/loaders/mongo_utils.py`, `AGENTS.md`.

## Shared navigation and state

`app.py` builds expanded sidebar navigation and includes a page only if its source file exists.

| Navigation section | Pages | Source |
| --- | --- | --- |
| Overview | Home; Area & Year; About | `app.py`, `pages/01_Home.py`, `pages/02_Price_Area_Selector.py`, `pages/99_About.py` |
| Exploration | Weather Overview; Weather Explorer; Energy Production; Energy Consumption | `app.py`, `pages/10_*.py` through `pages/13_*.py` |
| Regional & Local | Price Areas Map; Snow Drift | `app.py`, `pages/20_*.py`, `pages/21_*.py` |
| Modelling | Sliding Correlation; SARIMAX Forecast | `app.py`, `pages/30_*.py`, `pages/31_*.py` |
| Quality & Diagnostics | STL & Spectrogram; SPC & LOF | `app.py`, `pages/40_*.py`, `pages/41_*.py` |

The global selector writes these session keys immediately on every render:

| Control/state | Options and default | Stored behavior | Source |
| --- | --- | --- | --- |
| Price area | `NO1`–`NO5`; default `NO1` or prior valid value | `selected_area` | `pages/02_Price_Area_Selector.py` |
| Year mode | Single year / Range; default Single year unless prior `selected_years` contains multiple years | Widget key `sel_year_mode` | same |
| Single year | 2021–2024; default 2024 or prior valid value | `selected_year` and one-element `selected_years`; Jan 1–Dec 31 in date keys | same |
| Year range | endpoints from 2021–2024; default 2021–2024 or prior range | `selected_year` is always the final year; also writes inclusive `selected_years`, `selected_start_date`, and `selected_end_date` | same |

Most pages independently fall back to `NO1` and 2024 when the selector has not run. Production and consumption pages instead stop until both legacy keys exist. The map uses `selected_area` only to outline a polygon; its date, data kind, and group are local controls. Snow Drift uses the map's `clicked_coord`, independent of the global area/year. No page persists selection in the URL.

The range state is not consumed by the analytical pages in the current code. Weather, energy, correlation, SARIMAX, STL/spectrogram, and SPC/LOF read only the final `selected_year`; the map and Snow Drift use their own date controls. Migration must therefore treat range support as pending rather than existing parity.

## Page inventory

### Home and About

| Page | Controls and defaults | Visible behavior and edge cases | Source |
| --- | --- | --- | --- |
| Home | Expanded Quick start expander; collapsed Under the hood expander; navigation links | Static capability, data, caching, and missing-value notes. Links are shown only when their target file exists. Claims energy coverage of 2021–2024 and UTC presentation. | `pages/01_Home.py` |
| About | Navigation links only | Static quick start, source/technology notes, original-repository link, and 2021–2024 coverage claim. Suggests manual rerun if a view looks stale. | `pages/99_About.py` |

Neither page queries data, calculates metrics, or exports content.

### Weather Overview

There are no page-local controls. It reads the active area and final selected year, then requests the full year.

| Output | Current calculation/default | Empty/error behavior | Source |
| --- | --- | --- | --- |
| Summary table | For each available temperature, precipitation, wind speed, wind gust, and wind direction column: whole-frame min, arithmetic mean, max, plus an hourly sparkline for the first calendar month present | Missing expected columns are omitted. An empty frame is not guarded before finding the first month. Network/schema errors are not caught in the page. | `pages/10_Weather_Overview_Stats_and_Sparklines.py` |
| Monthly bars | Calendar-month sum for precipitation; arithmetic mean for temperature, wind speed, and gust | Missing months remain null after reindexing to months 1–12 | same |
| Annual direction rose | Counts direction observations in 16 bins of 22.5 degrees; exactly 360 degrees is mapped to 0; North is displayed at the top clockwise | Shows an info message if no valid directions exist. Frequencies are raw counts, so missing coverage changes totals. | same |

### Weather Explorer

| Control | Range/options | Default | Source |
| --- | --- | --- | --- |
| Variables | Available subset of five standard weather fields | All available fields | `pages/11_Weather_Explorer_Multi_Series_and_Resampling.py` |
| Month range | First through last month present | Full available frame | same |
| Normalize 0–1 | On/off | On | same |
| Rolling mean | 0–240 hours, step 1 | 24 hours; 0 disables | same |
| Resample | Hourly, Daily, Weekly | Hourly | same |
| Line opacity | 0.1–1.0, step 0.05 | 0.9 | same |

Processing order is month filtering, long-form reshape, optional resampling, optional time-window rolling mean, then per-variable min/max normalization. Daily/weekly precipitation is summed; other variables are averaged. A constant series uses span 1 and becomes zero after normalization. Wind direction is treated as an ordinary linear value during resampling and smoothing, despite being circular. The page stops on no selected variables, warns and stops on an empty selected range, and otherwise renders a WebGL line chart with range slider. It does not guard an entirely empty weather response before deriving month options.

### Energy Production and Energy Consumption

| Control | Options/default | Output behavior | Sources |
| --- | --- | --- | --- |
| Month | `01`–`12`; default `01` | Selects the hourly line-chart month | `pages/12_Energy_Production.py`, `pages/13_Energy_Consumption.py` |
| Groups | Production groups discovered across 2021–2024; consumption groups discovered from the collection | All discovered groups selected | same |

Both pages show a donut of annual total kWh by group and hourly group lines for the selected month. Hourly duplicates are summed by timestamp/group. Empty totals or hourly queries produce an info message.

Production totals use the legacy `prod_year_totals` collection in 2021 when present; otherwise they aggregate hourly records. Production group discovery catches and suppresses per-year collection errors. Consumption always aggregates `elhub_consumption_mba_hour`. Clearing the group multiselect produces an empty filter tuple, which removes the group predicate and therefore behaves as **all groups**, even though the UI shows no group selected.

### Price Areas Map

| Control/state | Range/options | Default | Source |
| --- | --- | --- | --- |
| GeoJSON | Sorted `data/*.geojson` files | Prior `map_geojson_path`, otherwise first sorted file | `pages/20_Price_Areas_Map_Selector.py` |
| Data source | Production / Consumption | Production | same |
| Group | Production: hydro, wind, solar, thermal, nuclear, other; Consumption: household, cabin, primary, secondary, tertiary | Solar for production; household for consumption | same |
| Interval | 1–365 days | 30 | same |
| End date | Date input | 2024-12-31 UTC label; query ends at 23:59:59 | same |
| Map click | Arbitrary latitude/longitude | Prior `clicked_coord`, otherwise no selection | same |

The page detects a GeoJSON property containing values normalizable to `NO1`–`NO5`, queries mean hourly `quantity_kwh` per detected area over the inclusive interval, and renders a four-step choropleth plus a sorted value table. Equal min/max values are separated by adding 1 to the scale maximum. The global selected area controls outline weight only. A click is rounded to six decimals for rerun comparison, saved at full float precision, marked on the map, and handed to Snow Drift; it does not change `selected_area` or require the point to lie inside Norway.

Production queries both legacy and newer collections and, when both return an area, take the unweighted mean of their already-aggregated means. This can differ from the record-weighted mean for a range spanning the collection boundary. Missing Folium packages, absent/undetectable GeoJSON, or an empty query stop the page with guidance. Database failures are not caught.

### Snow Drift

The page stops until `clicked_coord` exists. It calls an Open-Meteo historical-weather endpoint for that exact point and explicitly requests UTC timestamps; model identity is not preserved from response metadata.

| Control | Range/options | Default | Source |
| --- | --- | --- | --- |
| Maximum transport distance `T` | 100–10,000 m, step 100 | 3,000 m | `pages/21_Snow_Drift.py` |
| Fetch distance `F` | 1,000–200,000 m, step 1,000 | 30,000 m | same |
| Relocation coefficient `theta` | 0–1, step 0.05 | 0.5 | same |
| Season range | 2000–2024, inclusive start years | 2021–2024 | same |
| Fence type | Wyoming; Slat-and-wire; Solid | Wyoming | same |

Each season runs July 1 through June 30. The maximum choice of 2024 requests data through 2025-06-30. The page shows the first 24 source rows, a seasonal transport table/line, an average 16-sector transport rose, optional fence heights, a selected-season average monthly chart, and a monthly-by-season table. It labels seasonal/monthly transport in tonnes per metre after dividing kg/m by 1,000.

Embedded Tabler calculations:

- Hourly snow-water-equivalent contribution is precipitation when temperature is below +1 degrees C, otherwise zero; seasonal `Swe` is its sum in mm.
- Potential transport is `Qupot = sum(u^3.8 * 3600) / 233847` kg/m.
- `Qspot = 0.5 * T * Swe`; `Srwe = theta * Swe`.
- If `Qupot > Qspot`, `Qinf = 0.5 * T * Srwe` and control is snowfall; otherwise `Qinf = Qupot` and control is wind.
- `Qt = Qinf * (1 - 0.14^(F/T))` kg/m.
- Directional transport applies the same wind-power term to 16 nearest sectors and averages sector totals across available seasons.
- Fence height is `(Qt_tonnes / factor)^(1/2.2)`, with factors 8.5 (Wyoming), 7.7 (Slat-and-wire), and 2.9 (Solid).
- Monthly Qt repeats the full Tabler calculation within each month; the bar chart averages corresponding July–June months across seasons, while its comparison line is average full-season Qt.

The page catches request errors and stops on empty data/results. It does not label incomplete seasons or validate expected hourly coverage. Numeric weather nulls are not cleaned consistently; a null wind value can propagate into transport. The response's unit metadata is ignored, while the wind column is labeled m/s and used directly in a power-law calculation. This unit assumption needs explicit runtime/source verification before migration.

### Sliding Correlation

| Sidebar control | Range/options | Default | Source |
| --- | --- | --- | --- |
| Energy kind | Production / Consumption | Production | `pages/30_Sliding_Correlation.py` |
| Energy group | Six production or five consumption groups | First option: hydro or household | same |
| Weather variable | Five standard weather fields | Temperature | same |
| Window | 12–720 hours, step 6 | 168 hours | same |
| Lag | -240 to +240 hours | 0 | same |
| Normalize plot | On/off | On | same |
| Month | `01`–`12` | `01` | same |

The page limits both series to one selected month of the final selected year. Weather is hourly arithmetic mean and energy is hourly sum. Positive lag moves the weather index forward. The two series are intersected and pairwise null rows dropped; correlation is centered rolling Pearson `r` requiring a full window. Z-score normalization uses population standard deviation and affects only the upper comparison plot, not correlation. Constant plotted series become zeros.

The page stops on a missing weather variable, empty series, or fewer aligned observations than the selected window. At the 720-hour maximum, many calendar months cannot meet the full-window requirement. Wind direction can be correlated as a linear variable. Loader/network/database errors are not caught at page level.

### SARIMAX Forecast

| Sidebar control | Range/options | Default | Source |
| --- | --- | --- | --- |
| Energy kind/group | Production or Consumption; fixed group lists | Production / hydro | `pages/31_SARIMAX_Forecast.py` |
| Frequency | Hourly / Daily | Hourly | same |
| Training dates | Date range | Jan 1–Dec 31 of final selected year | same |
| Forecast horizon | 1–2,000 steps | 168 hourly; 30 daily | same |
| Weather regressors | Any of five weather fields | None | same |
| Future weather strategy | `last`; `hod-mean` | `last` | same |
| Nonseasonal order | p 0–5, d 0–2, q 0–5 | `(1,1,1)` | same |
| Seasonal enabled | On/off | On | same |
| Seasonal order | P 0–5, D 0–2, Q 0–5; s 2–336 hourly or 2–60 daily | `(1,0,1,24)` hourly; `(1,0,1,7)` daily | same |
| Dynamic in-sample prediction | On/off; start 0–100%, step 5 | On at 70% | same |
| Rolling backtest | On/off | On | same |
| Baseline lag `m` | 1–336 hourly or 1–60 daily | 168 hourly; 7 daily | same |
| Backtest horizon | 1–2,000 | 168 hourly; 7 daily | same |
| Cutoff step | 1–2,000 | 24 hourly; 1 daily | same |
| Folds | 1–25 | 5 | same |
| Also evaluate no-exog model | On/off | On only when regressors are selected; otherwise off | same |

Hourly energy is regularized and missing quantities are filled with zero. Hourly precipitation nulls become zero; other weather values interpolate up to six positions. Selected exogenous fields are reindexed to energy, interpolated up to six positions, then backfilled and forward-filled. Daily energy and precipitation are sums; other weather fields are arithmetic means. Wind direction is therefore treated linearly.

The model disables stationarity and invertibility enforcement. It renders actual, optional in-sample fitted, forecast, nominal 95% confidence interval, training-end line, and optional dynamic-start line. `last` repeats the final weather row into the horizon. Hourly `hod-mean` uses training means by hour of day; daily `hod-mean` actually uses day-of-week means. The page exposes AIC and model settings but no coefficient or residual diagnostics.

The rolling-origin evaluation compares a seasonal-naive repetition with SARIMAX without and/or with exogenous data, reporting per-model mean and standard deviation for MAE, RMSE, and MASE plus the last fold plot. Minimum training size is the maximum of 60 points, twice the baseline season, and a term based on AR/MA orders. Requested early folds that lack this history are discarded. Individual SARIMAX fit failures return `None` and are omitted from results without a failure count, so models can be averaged over unmatched folds. The page statement that MASE below one means the model beats the displayed seasonal-naive forecast is not generally valid: MASE uses an in-sample seasonal-error scale, not the held-out baseline error.

Additional migration checks include zero-filling missing energy, whole-span backfill of weather, synthetic rather than issue-time future weather, uncertainty intervals that omit weather uncertainty, absent cancellation/resource limits, missing validation for start after end, and possible missing hour/day groups in `hod-mean`. Model fit/forecast exceptions are displayed; empty energy and insufficient backtest history receive page messages.

### STL and Spectrogram

| Control | Range/options | Default | Source |
| --- | --- | --- | --- |
| Dataset/group | Production/Consumption and fixed group list | Production / solar | `pages/40_STL_Decomposition_and_Spectrogram.py` |
| STL period | 1–2,000 hours | 24 | same |
| STL seasonal smoother | 3–9,999, step 2 | 13 | same |
| STL trend smoother | 3–9,999, step 2 | 365 | same |
| Robust STL | On/off | On | same |
| Spectrogram window | 8–4,096 hours | 168 | same |
| Spectrogram overlap | 0–4,095 hours | 84 | same |

The page loads exactly the final selected calendar year and chosen group, previews 30 rows, then shows four STL components and a spectrogram. STL converts timestamps to UTC, sums to hourly bins only when pandas cannot infer frequency, coerces even smoother values to the next odd integer, and fits observed/seasonal/trend/residual in kWh. The spectrogram always resamples hourly by sum, interpolates gaps of up to three hours, fills all remaining gaps with zero, uses a Hann window, linear detrending, density scaling, magnitude mode, and displays 0–12 cycles/day.

Empty source data stops the page. Parameter compatibility is not validated in the UI: overlap may equal or exceed window length, a window may exceed available observations, and STL constraints/sample requirements may be violated. Analysis exceptions are not caught. The setup JSON records the effective STL parameters; there is no dedicated export of the component arrays or spectral matrix with provenance.

### SPC and LOF

| Tab/control | Range | Default | Source |
| --- | --- | --- | --- |
| SPC DCT fraction | 0.001–0.05, step 0.001 | 0.01 | `pages/41_SPC_and_LOF_Data_Quality.py` |
| SPC band width | 1–6 robust sigma, step 0.1 | 3 | same |
| LOF contamination | 0.001–0.05, step 0.001 | 0.01 | same |
| LOF neighbors | 10–120, step 5 | 60 | same |

The page loads the final selected area's/year's weather and exposes two tabs. SPC regularizes temperature to hourly, interpolates gaps of up to six hours, then forward/backfills any remaining nulls. It retains `max(1, floor(n * keep_fraction))` DCT coefficients for the trend. Robust sigma is 1.4826 times MAD, falling back to standard deviation and finally 1. Bounds are trend plus/minus `k * sigma`; strict outside points are flagged and SATV is residual divided by sigma. Fewer than 24 non-null points produces no analysis. The UI reports points, flags, percentage, sigma, maximum absolute SATV, a chart, and the first 30 flags.

LOF replaces nonnumeric or missing precipitation with zero and creates two unscaled features: current precipitation and a 24-row rolling mean. Effective neighbors are capped relative to frame length; the page first requires at least ten positive-precipitation rows. It reports scores/flags, a chart, and the first 30 flags. Missing required columns, sparse precipitation, and empty analysis produce messages. External load errors and analysis exceptions are not caught. These flags are statistical candidates, not verified data faults.

## Export inventory

There are **no custom application export controls or provenance-aware export contracts**: no page calls Streamlit's download widget. Runtime inspection of the pinned environment did reveal framework-provided **Download as CSV** on dataframes and **Download plot as a PNG** in Plotly toolbars. These were missed by the original source-only inventory. Preserve these existing conveniences during migration; adding exports of all displayed analysis values with area, interval, aggregation, units, provenance, and missing-data metadata remains pending under Phase 3. Framework toolbar visibility does not establish that exported content is complete or scientifically labeled.

## Data access, time, aggregation, and caching contracts

| Concern | Current behavior | Source |
| --- | --- | --- |
| Energy storage | Production 2021 uses `prod_hour`; later production uses `elhub_production_mba_hour`; consumption uses `elhub_consumption_mba_hour`; optional 2021 production totals use `prod_year_totals` | `app_core/loaders/mongo_utils.py`, `app_core/loaders/elhub_year.py`, `app_core/loaders/elhub_span.py` |
| Energy bounds | Year loader uses half-open `[Jan 1, next Jan 1)`; span loader and correlation series use inclusive end; page month queries use half-open month bounds; map uses inclusive seconds | relevant files in `app_core/loaders/`, pages 12, 13, 20, 30, 31 |
| Weather area proxy | One fixed city coordinate per price area: Oslo, Kristiansand, Trondheim, Tromso, Bergen | `app_core/loaders/weather.py` |
| Weather identity/units | Loader name says ERA5 but does not pass an explicit model. It requests legacy wind field names, does not request wind units, and ignores API unit metadata. | `app_core/loaders/weather.py`; point variant in `pages/21_Snow_Drift.py` |
| Timezone | Shared weather loader asks Open-Meteo for `Europe/Oslo`, receives timestamps parsed without timezone, and pages later pass them through `pd.to_datetime(..., utc=True)`. This treats the returned clock labels as UTC rather than explicitly converting from Oslo time. Other UI text says all times are UTC. | `app_core/loaders/weather.py`, weather-consuming pages |
| Page caches | Weather overview/explorer/SPC: 30 min; shared weather loader: 6 h; energy page queries: 10 min and group discovery: 30 min; map aggregation: 15 min and GeoJSON: 24 h; Snow Drift point weather: 1 h; forecast energy: 15 min/weather: 30 min/backtest: 15 min; STL data: 15 min | page decorators and `app_core/loaders/weather.py` |
| Missing values | Behavior varies: pairwise drop for correlation; zero-fill energy and precipitation in forecast; interpolation plus edge fill for forecast regressors/SPC; interpolation then zero-fill in spectrogram; direct propagation possible in Snow Drift | page/helper sources above |

The timezone and wind-unit items are high-priority contract checks because they affect timestamps, aggregation boundaries, correlation lags, and wind-powered calculations. The fixed-city weather proxy also needs to remain visible until any spatial replacement is validated.

## Existing automated verification and gaps

The test suite was inspected for this inventory. The separate [Phase 0 baseline](BASELINE.md) records all 49 tests passing. Current unit tests cover loader collection routing and time slicing, hourly energy sums, weather request shape/sorting, z-score behavior, lag/alignment/rolling correlation, SPC/LOF helper basics, STL component creation/odd-window coercion, spectrogram shapes/unit-axis conversion, SARIMAX metric basics, seasonal naive, `last` future exogenous values, daily aggregation, and a rolling backtest with SARIMAX replaced by a dummy.

Important gaps for parity work:

1. No Streamlit page/navigation/control test exercises defaults, session-state handoff, stop/error states, charts, map clicks, or display tables.
2. [Representative results and timings](BASELINE.md) are recorded; migration checks must cover the behavior being replaced rather than require a separate snapshot framework.
3. No tests cover selector range consumption or URL persistence; current pages do not implement either behavior.
4. No tests cover Weather Overview/Explorer calculations, circular wind handling, empty/full-year responses, DST conversion, API unit metadata, or actual model identity.
5. No tests cover annual energy totals, the legacy 2021 totals branch, group discovery, clear-all group semantics, map aggregation/GeoJSON detection, or cross-collection weighting.
6. Snow Drift and fence calculations are embedded in the page. The reference capture now includes partial-season transport and sector fixtures from unchanged page functions; fence heights, monthly outputs, coverage/completeness checks, unit assertions and scientific-assumption tests remain unverified.
7. The reference capture now fits real statsmodels SARIMAX without exogenous inputs over three matched folds and reconciles their metrics. The forecast page itself, `hod-mean`, confidence interval behavior, dynamic prediction, fold failure reporting, exogenous evaluation and MASE interpretation still need focused acceptance checks.
8. STL/spectrogram invalid parameter combinations and missing-data choices are not tested. SPC edge filling and LOF's zero imputation, neighbor limits, feature scaling, and time ordering lack focused coverage.
9. Framework-provided CSV/PNG downloads exist, but their contents and completeness have no tests; no custom metadata/provenance export contract exists.

These gaps are baseline facts and migration work items. They should not be resolved by deleting or silently changing Streamlit behavior before replacement acceptance checks are defined and passed.
