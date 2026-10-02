# Data pipeline

The Streamlit app reads a validated public Elhub snapshot from `data/energy.sqlite` when present. Without a snapshot it retains the existing MongoDB fallback. SQLite is a rebuildable local snapshot, not a migration or deletion of the research database. Original CSVs and notebooks remain unchanged.

## Run

From the repository root, with the project dependencies installed:

```bash
python scripts/refresh_data.py backfill
python scripts/refresh_data.py refresh
streamlit run app.py
```

Backfill fetches 2021 through the latest completed Elhub day and available ERA5 weather for all five area coordinates. Refresh reconciles the recent seven Elhub days plus any newer missing dates, and checks the current and previous weather years. Complete historical weather snapshots are reused; the current year is fetched again, and missing or incomplete historical snapshots are fetched as needed. `--skip-weather` limits either command to energy. Data snapshots are ignored by Git; they are application inputs, not baseline test artifacts.

The daily GitHub workflow runs at 19:37 UTC and can also be started manually. It restores the last usable snapshot, refreshes it (or backfills if the cache was evicted), and publishes the `validated-public-data` artifact when data validation and the freshness policy below pass. Download that artifact into `data/` to use it locally. Logs remain in the workflow, and energy refresh outcomes are recorded in SQLite. The workflow is enabled by publishing it to `origin/main`; it does not depend on this computer staying awake.

### Weather source outages

The scheduled workflow uses `refresh --weather-grace-days 7`. If the latest weather year cannot refresh, an existing validated snapshot can be retained when both its coverage is at most seven days behind the expected ERA5 boundary and its last successful retrieval is at most seven days old. The five-day ERA5 publication lag is separate, so this permits observations roughly twelve days behind today. Original observations, coverage dates, and retrieval times remain unchanged. Missing readings are never filled or invented.

These runs complete with **degraded** weather freshness: energy updates are kept, every weather area is attempted, and GitHub shows warning annotations and a freshness summary. Each downloadable data artifact includes `refresh-report.json` with the run outcome and per-area coverage, retrieval time, expected boundary, and source error. A separate `refresh-health` artifact preserves this report even when the job fails. The report is written beside the database, or to `--report PATH`.

The grace period applies only to refreshes of the latest year available from the source, including the previous calendar year during ERA5's New Year delay. Historical failures, unavailable snapshots, invalid freshness metadata, expired grace periods, and energy failures remain fatal. Cache saves and data uploads remain conditional on passing this policy. Local commands are strict unless the grace flag is explicitly supplied; backfills remain strict. A later successful source response automatically restores normal freshness. This workflow prepares downloadable data; updating the live dashboard still follows [release operations](RELEASE.md).

## Contracts

- Energy: kWh per hour, unique `(UTC timestamp, area, kind, group)`. Stored source, retrieval time, source revision time and quality accompany each value. Retrieval/revision metadata must not be mistaken for historical forecast-time availability.
- Requests use Oslo-local dates in chunks of at most 28 days. Responses preserve their UTC offsets before normalization. The global coverage display converts to Europe/Oslo with CET/CEST labels; analytical axes and date controls remain explicitly UTC. Internal queries are half-open `[start, end)`; user-facing inclusive dates become next-day exclusive boundaries. The local 2021 backfill begins at `2020-12-31T23:00:00Z`.
- No absent category is invented as zero. In particular, early 2021 NO5 wind is absent. Consumption aliases (`industry`, `private`, `business`) and unspecified `*` records are kept separate from base-group totals. The source does not define `*` sufficiently to treat it as a total.
- Validation rejects duplicate keys, non-finite/negative energy, malformed intervals, internal series gaps and truncated area coverage. Refresh also rejects disappearing observations in previously published overlap. An invalid or failed energy run cannot publish its staging snapshot.
- Weather: explicitly `era5_seamless`, UTC, wind m/s, temperature °C and precipitation mm. Annual atomic snapshots include coordinates, requested model/variables/units, retrieval time and actual available boundaries. The five-day source lag bounds requests; observed coverage determines usable dates. A failed refresh retains the prior snapshot and reports it as stale.
- Weather requests share a three-attempt budget for transient connection/HTTP failures and invalid source responses, with bounded backoff. Internal gaps remain invalid even if newer hours are present. If all attempts fail, the prior validated snapshot is retained only under the explicit grace policy above; otherwise the command exits unsuccessfully. Persistent gaps remain visible in the refresh report and require the upstream source to recover.
- Each area's selectable history is distinct from the all-series complete window. Energy/weather analyses must use their overlapping observed dates. Partial current-year comparisons use equal calendar/hour cutoffs, exclude unmatched February 29 observations, and suppress changes when either side has missing hours.
- Missing observations remain missing. Daily forecast aggregates require all 24 UTC hours. STL, spectrogram and LOF decline incomplete inputs instead of interpreting unknown values as zero.

## Verification

Tests cover daylight-saving days, units, missingness, leap-day/YTD comparisons, duplicate ingestion, revisions, transient retries and outage preservation. Run `python -m pytest -q`. Before pushing, run `python scripts/check_secrets.py --history`.

Live verification and reconciliation results are recorded in the Phase 1 section of the [implementation plan](IMPLEMENTATION_PLAN.md). The MongoDB history cannot be compared without its local credentials; public 2021–2024 data is fetched afresh and the tracked 2021 production CSV provides the available historical overlap check.

Sources: [Elhub API specification](https://api.elhub.no/energy-data/v0/openapi.yaml), [Elhub group metadata](https://api.elhub.no/energy-data/v0/consumption-groups), [Open-Meteo model and unit documentation](https://open-meteo.com/en/docs/historical-weather-api). Attribute energy to Elhub and weather to Open-Meteo and its ERA5/ERA5-Land providers when redistributing results.
