# Norwegian Energy Dashboard

Norwegian energy and weather analytics, delivered as a Next.js dashboard with a FastAPI backend.

The current application covers energy exploration, weather, regional maps, snow drift, diagnostics, and forecast evaluation. The former Streamlit app is retired.

## Features

- Production and consumption across Norwegian price areas (NO1–NO5)
- Weather exploration and regional analysis
- Correlation, decomposition, spectral, and data-quality views
- Forecast benchmarks, uncertainty metrics, and bounded custom jobs
- Transparent methods, data freshness, and provenance

## Quick start

Requirements: Python 3.11 or 3.12 and Node.js 22.

Install the development environment and generate the offline fixture:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/create_fixture.py
npm --prefix frontend ci
```

In one terminal, start the fixture API:

```sh
ENERGY_DATABASE=data/fixture/energy.sqlite \
WEATHER_SNAPSHOT_DIR=data/fixture/weather \
FORECAST_ARTIFACT_ROOT=data/fixture/forecasts \
ENERGY_DATA_MODE=fixture \
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal, start the dashboard:

```sh
cd frontend
npm run dev
```

Open <http://localhost:3000>. The fixture uses synthetic data and is labelled in the interface.

For real observations, deployment, data refresh, and rollback instructions, see [docs/RELEASE.md](docs/RELEASE.md).

## Checks

```sh
python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/` | FastAPI API and forecast jobs |
| `frontend/` | Next.js dashboard |
| `app_core/` | Reusable loaders and analysis functions |
| `tests/` | Python tests |
| `data/` | Published and fixture data |
| `docs/` | Architecture, release, and validation documentation |
| `notebooks/` | Historical exploratory research |

Read the [implementation plan](docs/IMPLEMENTATION_PLAN.md) for architecture and acceptance criteria. See [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md) for data commands and contracts.

## Data and security

Data sources are [Elhub](https://api.elhub.no/) and [Open-Meteo](https://open-meteo.com/). The dashboard does not require MongoDB credentials; retained research loaders use environment variables only.

Never commit credentials. Before pushing, run:

```sh
python scripts/check_secrets.py --history
```
