# Phase 2 validation

Recorded 2026-09-14. The local overview meets the initial latency targets. Keep Recharts for its current trend and use ECharts for the richer analytical views; the isolated trial remains available at `/chart-trial`. Streamlit continues to provide the broader application during migration.

## Chart-library trial

Evaluated 2026-09-14 on the isolated Next.js route `/chart-trial`. The route compares the existing Recharts 3.10.1 dependency with Apache ECharts 6.1.0 using rendered, interactive examples rather than a feature checklist.

### Recommendation

Standardize on **Apache ECharts for the analytical views that need zoom, heatmaps, polar wind roses, or geographic selection**. Keep the existing Recharts overview until it needs substantive revision: Recharts remains readable, React-native, and sufficient for its simple trend, while replacing it now would add migration risk without user benefit.

ECharts covered all five Phase 2 cases with one dependency and no React wrapper. Its `dataZoom`, heatmap, polar coordinate system, map series, event model, and modular imports reduce the custom geometry and interaction code that Recharts would require. The main tradeoffs are a larger dependency, an imperative lifecycle, canvas semantics that need HTML equivalents for important values and controls, and less direct React composition.

### Runnable cases

| Requirement | Recharts baseline | ECharts trial | Result |
| --- | --- | --- | --- |
| Time-series zoom | `Brush` | inside zoom plus slider | Both work; ECharts provides richer pointer zoom. |
| Uncertainty band | two stacked `Area` series | two stacked line-area series | Both work. The fixture is explicitly an illustrative 80% interval, not a forecast, and states omitted weather uncertainty. |
| Heatmap | No first-class heatmap in the documented chart list | heatmap series plus continuous visual scale | ECharts is clearer and substantially less custom. |
| Wind rose | Would require custom polar composition | polar bar series with 16 direction sectors | ECharts directly represents the required geometry. |
| Clickable map | No first-class map in the documented chart list | registered project GeoJSON, map selection, pan/zoom, click event | ECharts works with the repository's five real NO1–NO5 polygons. |

The heatmap keeps numeric cell labels, and the map mirrors canvas selection with keyboard-accessible HTML buttons and live text. All values are deterministic synthetic fixtures; only the map boundaries are repository geography. This avoids presenting generated values as observations or forecasts.

### Verification and limitations

The trial passed the frontend TypeScript check and production build and was inspected in a browser at desktop and 390 px widths. Direct checks covered ECharts slider zoom, the Recharts brush, a GeoJSON map click, the HTML area controls, initial map/HTML selection agreement, and responsive resizing. The route is lazy-loaded. The production manifests confirmed that its ECharts/trial chunk is absent from the overview route; that isolated chunk is 717,940 bytes raw and 236,344 bytes with gzip in this build. These figures describe this bounded trial build rather than a production performance target.

This is a bounded integration trial, not a full performance or accessibility certification. Canvas marks are not individually keyboard-operable; production charts must retain concise chart labels plus summaries, tables, or equivalent HTML controls. Runtime measurements should use the production deployment and representative record counts. The 2.1 MB GeoJSON should eventually be simplified or served as a versioned geography asset if map transfer or rendering becomes material.

### Official sources

- [Apache ECharts data zoom option](https://echarts.apache.org/en/option.html#dataZoom)
- [Apache ECharts heatmap series](https://echarts.apache.org/en/option.html#series-heatmap)
- [Apache ECharts polar coordinates](https://echarts.apache.org/en/option.html#polar)
- [Apache ECharts map series](https://echarts.apache.org/en/option.html#series-map)
- [Apache ECharts ARIA option](https://echarts.apache.org/en/option.html#aria)
- [Apache ECharts responsive container guidance](https://echarts.apache.org/handbook/en/concepts/chart-size/)
- [Recharts API and supported chart list](https://recharts.github.io/en-US/api/)
- [Recharts Brush example](https://recharts.github.io/en-US/examples/BrushBarChart/)
- [Recharts ranged Area examples](https://recharts.github.io/en-US/api/Area/)

## Performance comparison

This record compares server-side execution for the first replacement overview with its nearest retained Streamlit functions. The original `01_Home.py` is a navigation page and has no energy overview, so the retained `12_Energy_Production.py` and `13_Energy_Consumption.py` pages are the functional baseline. They are the unchanged pages present at overview commit `a7f6d6b840b947ee68c405f24751fa96fa6df8d5` and read the same local SQLite snapshot as the API. This does not reconstruct the pre-Phase 1 MongoDB application because doing so without its private database would not be a fair data-matched comparison.

### Method

The matched case is NO1 over UTC `[2025-01-01, 2026-01-01)`, a complete 365-day year. Streamlit AppTest executes each real page, including SQLite loading, Pandas aggregation, Plotly construction and Streamlit element serialization. It excludes the browser, paint and network. The harness replaces only `st.page_link`, because direct page-file AppTest has no multipage registry; data, controls, calculations and charts are unchanged. One descriptive cold observation per page clears Streamlit data/resource caches and the snapshot-metadata memo before creating AppTest. Operating-system file caches remain uncontrolled, so this is not a cold-process measurement and no cold percentile is claimed. Twenty warm observations then alternate the hourly-view month between January and July while retaining the loaded annual frame.

API observations call the running FastAPI service over persistent HTTP on the loopback interface. They include routing, SQLite work, response validation and JSON transfer, but exclude browser rendering. The first request is reported separately; median and p95 use 20 subsequent requests. p95 is the nearest-rank observation at `ceil(0.95 × n)`. No throttling was applied and machine load was uncontrolled. These boundaries differ, so the timings describe their respective server-side paths rather than an isolated framework speedup.

The API's suggested 28-day range is measured separately. It is representative of the new UI default but is not compared as if it matched the Streamlit pages: their year control loads annual totals and their month control changes only the hourly chart.

### Results

Recorded 2026-09-14 on macOS 26.6.2 arm64 with Python 3.11.13, Streamlit 1.63.0 and FastAPI 0.141.1. HEAD was `a7f6d6b840b947ee68c405f24751fa96fa6df8d5`; the measured backend working tree included the final-rounding correction described below. Source SHA-256 values were `f7212d903ddda6ec05fc0b7dcec5b8d629d9a31edc3b1aa2806be7736a0d1e29` for `backend/main.py`, `56ea73f319ad775a5bd4b8fd5a2a92d029507106cae238e2c6b1c7d9d280e133` for the production page and `998065fdc1bdd65d0ca7e5df6d13f7461d7d6d6ad20bffaf78072a5e4415b936` for the consumption page. The 644,128,768-byte `data/energy.sqlite` snapshot had SHA-256 `953e7803fc0be9df558d947845899fcad028ae116a11118af0a4ba0d774417b4`.

| Path | Measurement boundary | n | Median | p95 | Minimum | Maximum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Streamlit production, cold | AppTest, cache clear | 1 | 12,076.0 ms | — | 12,076.0 ms | 12,076.0 ms |
| Streamlit production, warm month filter | AppTest | 20 | 107.5 ms | 168.1 ms | 105.9 ms | 168.4 ms |
| Streamlit consumption, cold | AppTest, cache clear | 1 | 12,198.4 ms | — | 12,198.4 ms | 12,198.4 ms |
| Streamlit consumption, warm month filter | AppTest | 20 | 109.6 ms | 160.2 ms | 105.8 ms | 193.3 ms |
| API, matched calendar year | Persistent loopback HTTP | 20 | 229.9 ms | 256.4 ms | 223.1 ms | 262.6 ms |
| API, suggested 28 days | Persistent loopback HTTP | 20 | 17.8 ms | 27.3 ms | 17.2 ms | 41.0 ms |

The first measured API requests, which established their HTTP connections, took 522.8 ms for the calendar year and 41.8 ms for the suggested range `[2026-08-16, 2026-09-13)`. The retained-page loader and fixed API headline agreed within 0.001 MWh for the matched interval: production was 19,717,508.644 MWh and consumption was 32,421,589.593 MWh. Both kinds reported 8,760 observed and expected hours. An earlier review found that the API headline had summed values after rounding each day; the API test and implementation were corrected before this recorded run so the validation uses unrounded aggregates and rounds only the final result.

The warm server-path p95 values are below 500 ms; only the browser measurements below assess the filter-response target. The single cold AppTest observations do not establish a cold-start distribution. They show that the retained pages' metadata scan and annual-frame setup are expensive in this local harness. The API also scales materially with the requested interval: its annual warm median was about 13 times the 28-day median. Inspection points to the regional consumption ranking, which reads five groups for each of five areas in Python on every request, as a likely contributor; this is a code-informed hypothesis, not a component-level profile.

### Browser view

The browser run used the production Next.js 16.3.5 build with React 19.3.0 and Recharts 3.10.1 under Node 20.19.5. It ran in the Codex in-app browser at 1280 × 720 on the same macOS arm64 machine. The frontend at `localhost:3000` called the API at `localhost:8000` and used the same SQLite snapshot. OS, HTTP and asset caches were warm; there was no CPU or network throttle, and other benchmark/build work was paused. Browser samples preceded the final-rounding correction; it changes the headline summation but not the data queries or chart workload.

The page records `performance.now()` from navigation origin, or from the filter handler, through the second `requestAnimationFrame` after the matching overview response commits. The DOM markers `data-first-view-ms`, `data-update-ms` and `data-painted-query` identify the committed query. Navigation timing includes the coverage fetch, hydration, API request, React work, chart construction and a browser paint opportunity. Filter timing starts at the input handler and reuses the loaded coverage. It is a useful-view proxy, not compositor instrumentation. The default query was `[2026-08-16, 2026-09-13)`; the annual query was `[2025-01-01, 2026-01-01)`.

| Interaction | Input and cache state | n | Median | p95 | Minimum | Maximum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Default 28-day page load | Reload, warm OS/HTTP/assets | 20 | 95.85 ms | 105.2 ms | 86.2 ms | 180.2 ms |
| Default 28-day area filter | Mouse, alternating NO2/NO1 | 20 | 79.10 ms | 92.6 ms | 61.5 ms | 207.7 ms |
| Full-2025 page load | Reload, warm OS/HTTP/assets | 20 | 334.50 ms | 400.1 ms | 325.1 ms | 455.0 ms |
| Full-2025 area filter | Keyboard Enter, alternating NO2/NO1 | 20 | 300.25 ms | 401.2 ms | 277.4 ms | 531.6 ms |

A fresh-tab default view took 363.1 ms, and the first navigation to the full-year query took 770.9 ms. These are descriptive first observations with warm local services, not cold-process samples. All measured browser p95 values were below the 500 ms warm-filter target, and all first-view observations were below 2.5 seconds in this local setup. They do not establish deployed performance or behavior under throttling. These results do not justify adding caching layers or precomputed aggregates to the new overview now.

<details>
<summary>Raw browser samples in milliseconds</summary>

- Default reload: `180.2, 101.3, 102.0, 86.2, 90.1, 93.4, 95.7, 97.4, 86.8, 87.7, 93.2, 96.2, 102.3, 93.5, 99.3, 87.2, 92.2, 96.4, 105.2, 96.0`
- Default area filter: `90.8, 72.5, 89.5, 77.3, 90.5, 207.7, 61.5, 90.3, 63.6, 80.4, 92.6, 73.5, 71.3, 89.5, 72.3, 76.1, 73.0, 89.7, 77.8, 90.3`
- Full-2025 reload: `360.1, 396.0, 342.0, 332.9, 400.1, 325.1, 327.7, 345.4, 335.9, 333.0, 333.6, 335.0, 455.0, 376.1, 326.8, 398.6, 327.9, 326.7, 326.7, 334.0`
- Full-2025 area filter: `531.6, 316.5, 298.9, 285.4, 291.2, 306.5, 277.4, 296.1, 284.5, 301.1, 305.6, 302.2, 354.1, 296.9, 401.2, 368.1, 299.4, 293.5, 299.3, 316.6`

</details>

### Reproduce

Use the project environment and published snapshot. Start the API in one terminal, then run the benchmark from the repository root:

```bash
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
.venv/bin/python scripts/benchmark_overview.py
```

The script requires at least 20 observations for every percentile distribution, validates that both pages render the requested scope and two charts, independently sums the retained-page loader's five base groups for production and consumption, and fails unless both annual totals agree with the API headline within 0.001 MWh. It prints the snapshot SHA-256, byte size, Git commit, runtime versions, timings and validation totals as Markdown. Browser first-view and paint timings use a separate instrument described with their results because AppTest and HTTP do not measure them.
