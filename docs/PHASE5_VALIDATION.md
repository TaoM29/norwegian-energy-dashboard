# Phase 5 — Release candidate and Streamlit retirement

Recorded 2026-09-15. Streamlit retirement and the local release candidate are implemented. The full public-release gate remains open: no Internet deployment host/domain is configured. [GitHub CI passed for revision `441dbf8`](https://github.com/TaoM29/norwegian-energy-dashboard/actions/runs/34965254001), including the four Chromium journeys and Python 3.11/3.12. The additional changes recorded below are locally verified and remain uncommitted. No commit or push was made by the implementation agent.

## Retirement decisions

| Original capability | Replacement and acceptance evidence |
| --- | --- |
| Home, About, source provenance | Overview plus `/methods`: live snapshot coverage, original-project link, sources, walkthrough and limitations |
| Area/year selection | Shared area/date URL state; explicit date windows replace year/month controls |
| Production, consumption, weather overview/explorer | `/explore`; aggregation, circular direction, missingness and export verification in Phase 3 |
| Price-area map and point selection | `/regional`; real GeoJSON, weighted regional means, keyboard coordinates and pointer selection |
| Snow drift | `/regional`; retained Tabler calculations and validated source units, seasonal/monthly/sector outputs |
| Sliding correlation, STL, spectrogram, SPC and LOF | `/diagnostics`; numerical parity fixtures and Phase 3 browser evidence |
| SARIMAX, seasonal baseline, backtests and uncertainty | `/forecasts`; Phase 4 availability audit, matched evaluation, bounded jobs and held-out evidence |

The deliberate differences in [Phase 3](PHASE3_VALIDATION.md) and [Phase 4](PHASE4_VALIDATION.md) remain part of acceptance: strict missing grids, corrected circular/weighted aggregation, retrospective availability assumptions and bounded model complexity. They are not undocumented losses of functionality.

Removed `app.py`, the 13 Streamlit pages, their framework/unused map dependencies, and the old Streamlit performance runner. The runner and original application remain reproducible in a separate historical checkout, described in [release operations](RELEASE.md). Retained notebooks, sample source data, geography, analytical helpers, Python tests and historical validation. Small research compatibility loaders now use plain Python and environment variables rather than importing Streamlit; optional MongoDB use requires `pymongo` separately. Plotly remains because retained analytical helpers and tests still construct figures.

## Release work

- Pinned direct Python runtime dependencies and separated pytest into `requirements-dev.txt`; retained the frontend lockfile.
- Added Python/Node Docker images and a Compose stack with a persistent data volume, one API worker, health checks, rotating logs and an optional daily refresh process using the existing atomic publication path.
- Public Compose configuration disables custom forecast mutations. Stored results remain readable and the frontend hides the unavailable job forms. Local operators retain the bounded job runner and CLI.
- Added process liveness and energy readiness endpoints. Image-generated artifacts retain a supplied base commit and source fingerprint without requiring Git inside the runtime image.
- Added deterministic, explicitly labeled offline fixtures: 438,000 hourly energy rows across all areas/base groups, area weather, default-point snow weather, geography and 240 calculated seasonal-naive forecast rows. All generated files stay ignored under one `data/fixture/` directory. Fixture mode never falls through to an upstream weather request.
- Published `/methods` with live snapshot coverage, source attribution, four model cards, the short walkthrough, architecture, uncertainty caveats and three recorded findings. The numerical findings come directly from the Phase 2–4 validation evidence; fixture values are not presented as observations.
- Added four focused Playwright journeys to CI: overview filters/export, exploration/diagnostics/regional snow, prepared forecasts with public job rejection, and mobile methods/keyboard navigation. The workflows install offline fixtures and retain screenshots and failure traces for seven days. CI still tests Python 3.11 and 3.12.

## Local validation

The production images were built and started with Docker Engine 28.5.2 on macOS/ARM64. Both API and frontend containers reported healthy, using actual published data on `http://localhost:3001` and a separate synthetic deployment on `http://localhost:3002`. The API image does not contain Streamlit. Ordinary pages and stored forecasts work without it.

The recorded HTTP timings include the Next.js proxy and API over host loopback. Each row has six sequential requests: the first measured request and the median of the following five. These are local deployment measurements, not cold-machine, concurrent-load or Internet latency claims.

| Request | First measured (ms) | Subsequent median (ms) | Response bytes |
| --- | ---: | ---: | ---: |
| Energy readiness | 97.1 | 15.6 | 201 |
| NO1 August 2026 overview | 57.1 | 30.0 | 7,591 |
| Stored forecast list | 13.4 | 5.4 | 39,145 |
| Full Phase 4 benchmark | 50.6 | 26.0 | 881,161 |

Latest local Python suite: **177 passed**, with two existing dependency deprecation warnings. TypeScript checking and production builds passed both locally and in the frontend image. Compose configuration validated, both real/fixture deployments became healthy, and the runtime image confirmed that Streamlit is absent. Public job mutations returned 403 while stored results remained available.

Browser checks against the container deployment verified fixture labeling, overview area selection, exploration, rolling correlation, the default regional map/snow result, prepared forecasts with custom controls hidden, and Methods & Data source links/keyboard focus. Desktop and 820-pixel layouts were inspected in that session.

The follow-up ran all **four automated Chromium journeys successfully** against the isolated production test build and fixture API, including the **390-pixel mobile** layout and keyboard focus. Overview CSV checks compare row counts and exported MWh values with the selected API response. Forecast JSON checks cover fixture provenance, horizon, matched origins, calibration and frozen selection. Test builds now use `.next-e2e` so they cannot replace the normal application build. Screenshot inspection also caught and fixed a fixture banner hidden behind the desktop sidebar; the overview status label now says “Energy snapshot” rather than calling synthetic data observed. A reviewed [desktop/mobile gallery](screenshots/README.md) explicitly identifies its synthetic inputs.

Earlier checks caught and fixed a mismatched fixture point-cache key, an uncaught unavailable-weather exception, defaults outside fixture snow coverage, and observation-date navigation that hid prepared forecast points. The fixture API test explicitly rejects upstream network access.

Release review added container health for refresh failures, timeouts and overdue execution, with the last successful timestamp retained. Focused tests cover failure, recovery, timeout and stale status without making upstream calls. Rollback instructions now include the active refresh profile so code rollback also replaces the scheduler image. Energy readiness remains a readability/date-envelope check; internal observation gaps are supported rather than hidden or treated as application startup failures.

## Remaining public-release gate

Configure the actual host/domain and HTTPS proxy, publish the chosen real snapshots and prepared result artifacts there, enable its scheduled refresh, and measure the externally deployed journeys. Run CI again on the revision the user commits, capture the final public deployment screenshots, and verify the documented rollback on that host. The repository provides the runnable candidate and operations procedure; a loopback deployment is not an Internet release.
