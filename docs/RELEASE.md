# Release and operations

This release candidate uses Next.js and FastAPI. It needs one API worker because the bounded forecast queue is local to that process. Public configuration serves prepared results and disables custom fitting; a local development API enables bounded jobs by default.

## Clean setup and offline demonstration

Requires Python 3.11 or 3.12 and Node.js 22.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/create_fixture.py
cd frontend
npm ci
cd ..
```

Start the API with explicitly synthetic inputs:

```sh
ENERGY_DATABASE=data/fixture/energy.sqlite \
WEATHER_SNAPSHOT_DIR=data/fixture/weather \
FORECAST_ARTIFACT_ROOT=data/fixture/forecasts \
ENERGY_DATA_MODE=fixture \
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal, run `cd frontend && npm run dev`, then open `http://localhost:3000`. The yellow fixture banner distinguishes generated data from observations. Regenerating an existing fixture uses `python scripts/create_fixture.py --force`; recreate any fixture containers afterwards so their bind mounts use the replacement directory. The fixture includes every base group and area, weather and a genuinely calculated seasonal-naive evaluation. It does not manufacture evidence of model performance on real data. Point-weather fixture coverage is limited to the documented default point; other points return a clear fixture-coverage message without contacting the public source.

For real observations, run `python scripts/refresh_data.py backfill` from the repository root. Start the API without the fixture environment variables. Generate prepared forecasts with the command in [Phase 4 validation](PHASE4_VALIDATION.md). Ordinary views read published snapshots; point snow-weather requests are the exception. No MongoDB credentials are required by the dashboard.

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

The frontend listens on host loopback port 3001, and the API is only on the Compose network. Put the frontend behind the deployment host's HTTPS reverse proxy for public access. No hosting account, domain or production host is configured in this repository; these commands alone do not publish an Internet site.

To deploy the offline demonstration, set `DATA_DIR=./data/fixture ENERGY_DATA_MODE=fixture` before `docker compose up -d`. Never run the refresh profile against fixture data.

For a real-data deployment, enable the daily 19:37 UTC refresh worker:

```sh
docker compose --profile refresh up -d
```

The worker uses the same persistent volume and existing atomic refresh implementation. It logs failures and retains the last validated snapshots. The GitHub scheduled workflow separately publishes downloadable data artifacts; it does not update this host. Forecast benchmarks remain explicit versioned analyses: refreshes do not silently rewrite their historical results. Run `docker compose run --rm api python scripts/run_forecast_benchmark.py` with the chosen predeclared configuration when publishing another evaluation.

## Health, logging and limits

- `/api/health`: process liveness and published/fixture mode.
- `/api/ready`: checks the required energy-series coverage and reports the current snapshot. Weather and forecast availability are reported by their own endpoints; energy readiness is not a guarantee that every historical point request is cached.
- `docker compose ps` and `docker compose logs --tail=100 api frontend refresh`: service status and request/refresh logs. Container logs rotate at 10 MB, three files.
- Queries have date/parameter bounds; forecasting has one active worker, four queued jobs and a 30-minute timeout. `FORECAST_JOBS_ENABLED=false` rejects both job submission and cancellation and hides the experiment controls. Keep this setting on a public deployment. Local operators can run the CLI or a separate private API for experiments.
- Credentials remain backend-only environment variables. The new dashboard requires no MongoDB connection. Optional retained research loaders use `MONGO_URI` and `MONGO_DB` from the environment and require separately installed `pymongo`.

## Rollback

Retain the previous frontend/API image tags and a copy of the previous published data directory before a release. To roll back code, set `RELEASE_TAG` to the previous tag and run `docker compose up -d --no-build`; confirm `/api/ready`, `/api/forecasts/results` and the main views. If the data publication is the problem, stop the refresh service, select the retained data directory with `DATA_DIR`, and recreate the API and refresh services. Keep the same volume for routine code rollbacks. Immutable forecast artifacts remain readable across restarts.

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
ENERGY_API_URL=http://127.0.0.1:8100 npm run build
npx playwright install chromium
PYTHON="$(pwd)/../.venv/bin/python" npm run test:e2e
```

Use an absolute Python executable path for `PYTHON` if the environment differs; the API command runs from the repository root. CI installs Chromium, generates the fixture, checks types, builds and runs the journeys without live external data calls. Python CI retains 3.11 and 3.12.

Implementation references: [Next.js self-hosting](https://nextjs.org/docs/app/guides/self-hosting), [Compose health-based startup](https://docs.docker.com/compose/how-tos/startup-order/), [Playwright web servers](https://playwright.dev/docs/test-webserver). Actual local deployment measurements and remaining release gates are recorded in [Phase 5 validation](PHASE5_VALIDATION.md).
