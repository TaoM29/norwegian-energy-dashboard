# Norway Energy Atlas

Production, demand & weather analytics, delivered as a Next.js dashboard with a FastAPI backend.

The current application covers energy exploration, weather, regional maps, snow drift, diagnostics, and forecast evaluation. The former Streamlit app is retired.

Live dashboard: <https://norwegian-energy-dashboard.vercel.app>  
Source code: <https://github.com/TaoM29/norwegian-energy-dashboard>

## Features

- Production and consumption across Norwegian price areas (NO1–NO5)
- Weather exploration and regional analysis
- Correlation, decomposition, spectral, and data-quality views
- Saved weather-adjusted household-demand studies with temporal validation and uncertainty
- Forecast benchmarks, uncertainty metrics, and bounded custom jobs
- Transparent methods, data freshness, and provenance

## Tech stack

[![Next.js](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-0F172A?style=for-the-badge&logo=tailwindcss&logoColor=38BDF8)](https://tailwindcss.com/)
[![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-18181B?style=for-the-badge&logo=shadcnui&logoColor=white)](https://ui.shadcn.com/)

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-00695C?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![pandas](https://img.shields.io/badge/pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-9A4C00?style=for-the-badge&logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)

[![Apache ECharts](https://img.shields.io/badge/Apache_ECharts-AA344D?style=for-the-badge&logo=apacheecharts&logoColor=white)](https://echarts.apache.org/)
[![Vercel](https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)
[![Docker](https://img.shields.io/badge/Docker-1D63ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-1D4ED8?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)

The project combines an interactive **TypeScript frontend** with a **Python analytics backend**. Next.js and React handle the dashboard you see in the browser, while FastAPI connects it to energy data, weather observations, and statistical analyses.

| Layer | Technologies | What they do here |
| --- | --- | --- |
| Frontend | Next.js, React, TypeScript | Build the dashboard pages, interactive filters, and shared application state with typed components. |
| Interface | Tailwind CSS, shadcn/ui, Radix UI, Lucide | Provide styling, reusable controls, accessible interaction primitives, and icons. |
| Charts | Apache ECharts, Recharts | ECharts powers the advanced analytical views; Recharts renders the energy overview. |
| API | Python, FastAPI, Uvicorn | Serve data and analysis results to the frontend and run the API locally. |
| Analytics | pandas, NumPy, SciPy, statsmodels, scikit-learn | Prepare time-series data, explore patterns and anomalies, and build and evaluate forecasting models. |
| Data | SQLite, saved weather snapshots, prepared analysis and forecast files | Keep observations and computed results available without a live connection to a private database. |
| Deployment | Vercel, Docker Compose | Vercel hosts the public frontend and API; Docker Compose provides an alternative container-based deployment. |
| Quality checks | pytest, Playwright, TypeScript, GitHub Actions | Check Python behavior, browser workflows, type safety, and builds. |

**How it fits together:** energy observations from Elhub and weather observations from Open-Meteo are collected into local snapshots. The Python backend reads those snapshots and prepared analytical results, exposes them through FastAPI, and the Next.js frontend turns them into interactive charts and regional views. The public deployment serves saved forecast results; local development can also run bounded custom forecast jobs.

## Local development (optional)

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

The [statistical analysis roadmap](docs/STATISTICAL_ANALYSIS_ROADMAP.md) describes proposed next studies, their implementation order, and the evidence required to complete each step.

## Data and security

Data sources are [Elhub](https://api.elhub.no/) and [Open-Meteo](https://open-meteo.com/). The dashboard does not require MongoDB credentials; retained research loaders use environment variables only.

Never commit credentials. Before pushing, run:

```sh
python scripts/check_secrets.py --history
```
