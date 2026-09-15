# Norwegian Energy Dashboard

A Norwegian energy and weather analysis project evolving into a **Next.js / React frontend with a Python backend**.

**Status:** The dashboard now runs in Next.js and FastAPI. Overview, exploration, diagnostics, regional/snow and forecasting workflows are implemented. Phase 5 retires Streamlit and adds Methods & Data, an offline fixture, container release setup and browser CI. Public hosting remains a separate, unconfigured release step. Changes and validation are tracked in [Phase 5 validation](docs/PHASE5_VALIDATION.md).

## Implementation plan

Read the [implementation plan](docs/IMPLEMENTATION_PLAN.md) for the architecture, feature parity inventory, phased milestones, acceptance criteria, and statistical/ML research backlog.

The planned dashboard will combine:

- Energy production and consumption exploration across NO1–NO5.
- Weather exploration, regional maps, and snow-drift analysis.
- Correlations, decomposition, spectral analysis, and anomaly detection.
- Forecasting with realistic backtests, baseline comparisons, and uncertainty.
- Automated updates through the latest validated data, including available 2026 coverage.
- A responsive, accessible public interface with transparent methods and data freshness.

## Run locally

See [release setup](docs/RELEASE.md) for a clean installation, a no-network synthetic demonstration, Docker deployment and rollback. To use real observations:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/refresh_data.py backfill
```

No credentials are needed for the public data pipeline. The retained optional MongoDB research loaders use environment variables; they are not part of serving the dashboard. See [data pipeline commands and contracts](docs/DATA_PIPELINE.md).

Run Python checks with `python -m pytest -q`. The [Phase 0 baseline](docs/BASELINE.md) and [feature-control inventory](docs/FEATURE_CONTROL_INVENTORY.md) retain the original scientific and migration evidence. The [original README](docs/LEGACY_README.md) preserves the inherited project documentation.

## React dashboard

With the public-data snapshot above available, start the API from the repository root:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal (Node.js 20.9+):

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. The overview includes area/date filters, daily production and consumption, production mix, regional consumption, and an accessible values table. Filters persist in the URL. UI dates include both endpoints; the API uses UTC `[start, end)` ranges of at most 366 days and returns MWh. Charts display GWh and leave incomplete days as gaps.

`GET /api/coverage` returns the shared date envelope and suggested range. `GET /api/overview?area=NO1&start=2026-08-01&end=2026-09-01` returns the headline, daily series, mix and regional ranking together, with missingness and snapshot provenance. See http://127.0.0.1:8000/docs for query documentation. The API reads `data/energy.sqlite`; set `ENERGY_DATABASE` to use another published snapshot. Set `ENERGY_API_URL` before starting/building Next.js if the API runs elsewhere.

For frontend validation, run `npm run typecheck` and `npm run build` inside `frontend/`. The [Phase 2 validation](docs/PHASE2_VALIDATION.md) records the chart-library trial and matched performance comparison. The [Phase 3 validation](docs/PHASE3_VALIDATION.md) records exploration and diagnostics parity. Open `/explore` for energy/weather, `/diagnostics` for correlation, decomposition and statistical quality checks, and `/regional` for maps and snow drift. Open `/forecasts` for saved benchmarks, uncertainty metrics and cancellable custom jobs. The [Phase 4 validation](docs/PHASE4_VALIDATION.md) records the benchmark, availability assumptions and reproduction command. Forecast artifacts are stored locally under ignored `data/forecasts/`; use one API worker for its bounded job queue. Open `/methods` for sources, freshness, model cards and three recorded case studies. Open `/chart-trial` for the isolated, explicitly synthetic chart examples. Recharts remains in the overview; ECharts is selected for the richer analytical views.

## Current structure

| Path | Purpose |
| --- | --- |
| `app_core/` | Data loading and reusable statistical functions |
| `backend/` | FastAPI data, analysis, forecast artifacts and bounded jobs |
| `frontend/` | Next.js analytical workspaces with shadcn/ui, Recharts and ECharts |
| `tests/` | Python data, analysis and API tests |
| `data/` | Tracked sample data and geographical boundaries |
| `notebooks/` | Original exploratory research |
| `docs/` | Migration plan and historical documentation |

Streamlit pages and their framework dependency are retired. Useful notebooks, analytical helpers, tests, sample data and historical source remain available.

## Repository provenance

This is an independent continuation of [TaoM29/data-to-descision-dashboard](https://github.com/TaoM29/data-to-descision-dashboard), preserving its Git history from baseline commit `b3dd41d626153cebce2f2945ad1efc0a195d7bd7`. The original repository remains separate.

Development and future pushes belong to [TaoM29/norwegian-energy-dashboard](https://github.com/TaoM29/norwegian-energy-dashboard). The original Streamlit deployment is a reference to the earlier project, not a deployment of the planned Next.js dashboard.

Data sources: [Elhub](https://api.elhub.no/) and [Open-Meteo](https://open-meteo.com/). Dataset attribution and source/model provenance will remain visible in the new application.

## Credential handling and sanitized history

On 2026-09-14, this repository's history was rewritten to remove exposed MongoDB credentials and the previously committed `.streamlit/secrets.toml`. Commit IDs differ from the original repository, whose history was not modified. The baseline hash above identifies the original project's source commit.

The connection cell in `notebooks/part-2.ipynb` now requires `MONGO_URI` in the environment. Optional research loaders also use environment variables. Never commit credentials. Run `python scripts/check_secrets.py --history` before pushing; CI runs the same targeted check.

Credential removal does not revoke exposed passwords or remove copies in other repositories. Rotate affected database-user passwords in MongoDB Atlas and update applications using them. After this rewrite, use a fresh clone or carefully reset local branches; do not merge old history back into this repository.
