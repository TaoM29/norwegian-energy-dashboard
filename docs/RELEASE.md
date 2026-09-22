# Release and operations

This release candidate uses Next.js and FastAPI. Deployments that enable custom fitting need one API worker because the bounded forecast queue is local to that process. Public configuration serves prepared results and disables custom fitting; a local development API enables bounded jobs by default.

## Vercel production

- Dashboard: https://norwegian-energy-dashboard.vercel.app
- FastAPI: https://norwegian-energy-api.vercel.app
- Vercel scope: `taom29s-projects`.

Both projects connect to `TaoM29/norwegian-energy-dashboard`, with `main` as
production branch. Each push to `main` deploys both applications:

| Vercel project | Root directory | Framework | Build command |
| --- | --- | --- | --- |
| norwegian-energy-dashboard | frontend | Next.js | npm run build |
| norwegian-energy-api | repository root | FastAPI | python scripts/fetch_snapshot.py |

The dashboard's `ENERGY_API_URL` is `https://norwegian-energy-api.vercel.app`.
Next.js rewrites keep browser requests on the same origin. Production and preview
builds use that API. No local server or MongoDB connection is needed.

The API build downloads the public Vercel Blob archive pinned in
`data/snapshot.json`, verifies its SHA-256, and unpacks the real published
observations and saved forecast results. Git stores the manifest, not the large
dataset. The public archive contains observations and scientific results only;
it excludes local job records and configuration. Builds need no Blob write token.

Root `server.py` keeps SQLite read-only and copies weather/forecast caches to
temporary writable storage. Custom background fitting remains disabled. Python
3.12 and Vercel Large Functions support the scientific dependencies and database.
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` is configured on the API project.

To publish updated data:

1. Run the existing local refresh and any explicitly requested forecast analysis.
2. Run `python scripts/prepare_vercel.py` to package a consistent SQLite backup,
   weather, geography, saved forecasts, and the prepared demand-sensitivity, demand-anomaly and demand-change studies
   in `.vercel-deploy/api/snapshots.tar.gz`. All three studies are required; missing or empty files stop packaging before replacing the previous archive.
   The command prints the archive's SHA-256.
3. Upload it to the `norwegian-energy-snapshots` Vercel Blob store under a new path
   containing that hash. Keep previous archives for rollback; do not overwrite.
4. Update the URL and SHA-256 in `data/snapshot.json`. Commit and push the
   manifest with any code changes to `main` when ready.

The API build also rejects archives that omit any required saved study. Upload and verify the replacement archive before committing its URL and checksum with the code; an old sensitivity-only pin cannot serve the newer study pages. Keep the old archive with its matching API version for rollback.

Snapshots are fixed per commit; pushing UI code reuses the pinned data. The GitHub
refresh workflow publishes downloadable artifacts but does not change this pin.
Temporary point-weather caches do not persist across function instances.

Verify `/api/ready`, overview, weather, regional data, saved forecasts, and
Patterns → Demand sensitivity, Demand anomalies and Demand changes through the dashboard domain after deployment.
Roll back with Vercel's deployment history;
API and frontend releases are promoted independently. The older pinned archives
allow Git rebuilds to reproduce the same input data.

## Clean setup and offline demonstration

Follow the [README local setup](../README.md#local-development-optional) to install dependencies, generate the synthetic fixture, and start the API and frontend. The fixture banner distinguishes generated data from observations.

Regenerating an existing fixture uses `python scripts/create_fixture.py --force`; recreate any fixture containers afterwards so their bind mounts use the replacement directory. The fixture includes every base group and area, weather, a genuinely calculated seasonal-naive evaluation, and fitted synthetic demand-sensitivity and demand-anomaly studies plus a saved demand-change scan. It does not manufacture evidence of model performance on real data. Point-weather fixture coverage is limited to the documented default point; other points return a clear fixture-coverage message without contacting the public source.

For real observations, run `python scripts/refresh_data.py backfill` from the repository root. Start the API without the fixture environment variables. Generate prepared forecasts with the command in [Phase 4 validation](PHASE4_VALIDATION.md). Ordinary views read published snapshots; point snow-weather requests are the exception. No MongoDB credentials are required by the dashboard.

Prepare the fixed weather-adjusted demand study with `python scripts/run_demand_sensitivity.py` after the 2021–2025 snapshots are available. See [Step 1 validation](STEP1_VALIDATION.md) for the protocol, retained-input replay, and interpretation. The API reads `analyses/demand-sensitivity.json` beside `ENERGY_DATABASE`, or the file selected by `DEMAND_SENSITIVITY_ARTIFACT`; it never fits on page visits. Keep the result and its companion input directory for audit/replay. Missing studies produce an unavailable state. The Vercel packaging command requires the default prepared study; it does not upload or repin the public archive automatically. Containers read the same file from their data mount.

The broader forecast reliability study uses the [frozen Step 2 protocol](STEP2_PROTOCOL.md)
and `python scripts/run_forecast_reliability.py`. Retain its checksummed input
bundle under `data/analyses/` for replay. Its immutable result appears alongside
older results in Forecasts and is included by the normal snapshot packaging
command. A code push alone does not publish a newly fitted result: upload and
repin the data archive as above. Verify the new saved result's reliability panel
and metadata download after publishing it.

The [Step 4 feature ablation](STEP4_PROTOCOL.md) runs with
`python scripts/run_forecast_ablation.py` against those same retained Step 2
inputs. Keep its companion `data/analyses/*-runs` directory, including the
protocol, source archive and separate variant results. Its combined forecast
artifact is packaged by the same snapshot workflow. After publication, select
**Feature ablation · calendar, demand and weather** in Forecasts and verify the
comparison panel and complete JSON download. Local fitting does not update the
public site; committing code alone does not publish the new study.

The [Step 5 contextual demand anomaly study](STEP5_PROTOCOL.md) runs with
`python scripts/run_demand_anomalies.py` using the retained Step 1 input bundle.
The default result is `data/analyses/demand-anomalies.json`; retain its companion
`demand-anomalies-evidence/` directory and original Step 1 inputs for replay.
The API reads the result beside `ENERGY_DATABASE`, or from
`DEMAND_ANOMALIES_ARTIFACT`, without fitting on page visits. The fixture generator
also prepares a clearly labeled synthetic demonstration. Normal snapshot
packaging requires the default result. After publishing the archive,
verify **Patterns → Demand anomalies**, all five areas, candidate selection,
coverage and the complete JSON download. See [validation](STEP5_VALIDATION.md).

The [Step 6 demand-peak views](STEP6_VALIDATION.md) calculate descriptive summaries
from the existing published energy snapshot. No prepared study or new data source
is required. After a release, verify **Explore → Demand peaks** and
**Regional → Demand peaks**, including date changes, shared-hour coverage and
absolute/relative regional curves. The same endpoints work with the synthetic
fixture and identify it explicitly.

The [Step 7 daily profiles](STEP7_VALIDATION.md) also use the published household
energy snapshot directly. No clustering job, prepared study or additional data
source is required. Verify **Explore → Daily profiles**, both groupings and
scales, and the observed-day drill-down after a release. UTC picker dates remain
inclusive; the hourly profiles use Europe/Oslo local time. Confirm boundary and
23/25-hour DST exclusions remain visible and repeated autumn hours retain their
different offsets in the raw-day table and downloads.

Saved forecast detail and complete-artifact downloads stream the stored JSON
file. This preserves every prediction row while supporting studies larger than
Vercel's [buffered response limit](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions).

The [Step 8 demand-change study](STEP8_VALIDATION.md) is prepared explicitly with
`python scripts/run_demand_changes.py` after the saved observed Step 5 artifact is
available. Its protocol pins that source's identity and checksum. The runner
refuses to replace an existing result; retain `data/analyses/demand-changes.json`
and its `demand-changes-evidence/` companion for replay. Ordinary page requests
only read the saved result. `DEMAND_CHANGES_ARTIFACT` can override its location.
Snapshot packaging requires the result, so publishing requires an
updated snapshot as well as application code. Verify **Patterns → Demand changes**,
the visible calibration limitation, timeline/distribution switch, coverage,
sensitivity checks and JSON/CSV downloads. These are exploratory candidates;
synthetic false-alarm calibration did not meet the nominal 5% target. No forecast
error monitoring or live alerts are included.

## Container deployment

The Compose stack builds the frontend and API and mounts one persistent data directory. Supply a directory containing `energy.sqlite`, `weather/`, `forecasts/` and `file.geojson`. The repository's real `data/` directory already has the geography; fixture setup writes it too. Keep source data out of images and rebuilds. The VCS_REF build argument records the base commit in container-generated forecast metadata; source fingerprints distinguish uncommitted changes, and container dirty status remains unknown. Build tags identify rollback candidates; do not reuse a tag for different source.

```sh
export LOCAL_UID=$(id -u) LOCAL_GID=$(id -g)
export RELEASE_TAG=release-candidate
export VCS_REF=$(git rev-parse HEAD)
# DATA_DIR defaults to ./data; fixture demonstration can use ./data/fixture.
docker compose build
docker compose up -d
curl --fail http://127.0.0.1:3001/api/ready
```

The frontend listens on host loopback port 3001, and the API is only on the Compose network. Put the frontend behind the deployment host's HTTPS reverse proxy for public access. These container commands are an alternative to the Vercel deployment above and do not publish an Internet site by themselves.

To deploy the offline demonstration, set `DATA_DIR=./data/fixture ENERGY_DATA_MODE=fixture` before `docker compose up -d`. Never run the refresh profile against fixture data.

For a real-data deployment, enable the daily 19:37 UTC refresh worker:

Default energy refresh/backfill requests end at yesterday's Oslo midnight
(exclusive), allowing for Elhub's publication delay. Explicit service cutoffs
remain unchanged, and incomplete upstream responses still fail validation rather
than replacing the last good snapshot. This also applies when GitHub delays a
scheduled run past local midnight.

```sh
docker compose --profile refresh up -d
```

The worker uses the same persistent volume and existing atomic refresh implementation. It logs failures and retains the last validated snapshots. Its container health reports failed, timed-out or overdue refreshes through `data/refresh-status.json`, retaining the last successful run time. Restarting does not clear a failed run. To retry immediately, stop the scheduled worker, run `docker compose run --rm refresh python scripts/scheduled_refresh.py --once`, then restart the worker; this avoids overlapping writers. The GitHub scheduled workflow separately publishes downloadable data artifacts; it does not update this host. Forecast benchmarks remain explicit versioned analyses: refreshes do not silently rewrite their historical results. Run `docker compose run --rm api python scripts/run_forecast_benchmark.py` with the chosen predeclared configuration when publishing another evaluation.

## Health, logging and limits

- `/api/health`: process liveness and published/fixture mode.
- `/api/ready`: checks that required energy series are readable and reports their common date envelope. Internal missing hours remain visible as gaps in the analytical views; readiness does not certify complete observations. Weather and forecast availability are reported by their own endpoints; energy readiness is not a guarantee that every historical point request is cached.
- `docker compose ps` and `docker compose logs --tail=100 api frontend refresh`: service status and request/refresh logs. Container logs rotate at 10 MB, three files.
- Queries have date/parameter bounds; forecasting has one active worker, four queued jobs and a 30-minute timeout. `FORECAST_JOBS_ENABLED=false` rejects both job submission and cancellation and hides the experiment controls. Keep this setting on a public deployment. Local operators can run the CLI or a separate private API for experiments.
- Credentials remain backend-only environment variables. The new dashboard requires no MongoDB connection. Optional retained research loaders use `MONGO_URI` and `MONGO_DB` from the environment and require separately installed `pymongo`.

## Rollback

Retain the previous frontend/API image tags and a copy of the previous published data directory before a release. To roll back code, set `RELEASE_TAG` to the previous tag and run `docker compose --profile refresh up -d --no-build` when the deployment uses scheduled refresh, so the worker also rolls back. Omit `--profile refresh` when no worker is deployed (including fixture deployments). Then confirm `/api/ready`, `/api/forecasts/results` and the main views. If the data publication is the problem, stop the refresh service, select the retained data directory with `DATA_DIR`, and recreate the API and refresh services. Keep the same volume for routine code rollbacks. Immutable forecast artifacts remain readable across restarts.

Streamlit was retired after the Phase 3/4 parity checks. To investigate the old application or rerun `scripts/benchmark_overview.py`, use a separate checkout of commit `b2c46c0dcdcd7ab343470d022f7394d0e71b3646` with the historical environment in `docs/baseline/requirements-py311-macos.txt`. Do not merge pre-sanitization history into the current repository. Existing notebooks and analytical tests remain in the current tree.

## Checks

```sh
python -m pytest -q
cd frontend
npm run typecheck
npm run build
```

The focused browser journeys use the offline fixture and isolated ports 8100/3100:

```sh
python scripts/create_fixture.py
cd frontend
npx playwright install chromium
PYTHON="$(pwd)/../.venv/bin/python" npm run test:e2e
```

The test command builds into `.next-e2e`, leaving the normal `.next` build intact. CI retains screenshots and failure traces for seven days; a small reviewed [fixture gallery](screenshots/README.md) is included in the repository.

Use an absolute Python executable path for `PYTHON` if the environment differs; the API command runs from the repository root. CI installs Chromium, generates the fixture, checks types, builds and runs the journeys without live external data calls. Python CI retains 3.11 and 3.12.

Implementation references: [Next.js self-hosting](https://nextjs.org/docs/app/guides/self-hosting), [Compose health-based startup](https://docs.docker.com/compose/how-tos/startup-order/), [Playwright web servers](https://playwright.dev/docs/test-webserver). Actual local deployment measurements and remaining release gates are recorded in [Phase 5 validation](PHASE5_VALIDATION.md).
