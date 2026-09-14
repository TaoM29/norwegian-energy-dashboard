# Norwegian Energy Dashboard

A Norwegian energy and weather analysis project evolving into a **Next.js / React frontend with a Python backend**.

**Status:** Phase 1 data loading and correctness are implemented. Public energy data has been backfilled from 2021 through available 2026 observations, with validated UTC intervals, coverage-aware controls and atomic refreshes. The first Phase 2 overview now runs in Next.js with a Python API. Streamlit retains the broader analytical features during migration.

## Implementation plan

Read the [implementation plan](docs/IMPLEMENTATION_PLAN.md) for the architecture, feature parity inventory, phased milestones, acceptance criteria, and statistical/ML research backlog.

The planned dashboard will combine:

- Energy production and consumption exploration across NO1–NO5.
- Weather exploration, regional maps, and snow-drift analysis.
- Correlations, decomposition, spectral analysis, and anomaly detection.
- Forecasting with realistic backtests, baseline comparisons, and uncertainty.
- Automated updates through the latest validated data, including available 2026 coverage.
- A responsive, accessible public interface with transparent methods and data freshness.

## Current application

The inherited application uses Streamlit, Plotly, MongoDB, Open-Meteo, statsmodels, SciPy and scikit-learn. Date selectors use validated observed coverage, including available 2026 data.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Run `python scripts/refresh_data.py backfill` once to create the ignored local public-data snapshots; no credentials are needed. Energy pages use this snapshot, with optional MongoDB fallback via `.streamlit/secrets.toml` (`MONGO_URI`, optionally `MONGO_DB`). Weather retains the last validated snapshot during an outage. See [data pipeline commands and contracts](docs/DATA_PIPELINE.md). See the [preserved original README](docs/LEGACY_README.md) for the inherited project's documentation and original deployment links.

Run the existing Python tests from the repository root:

```bash
python -m pytest -q
```

See the [Phase 0 baseline](docs/BASELINE.md) for the tested environment, representative timings and historical capture evidence. The [feature-control inventory](docs/FEATURE_CONTROL_INVENTORY.md) records controls, exports and calculations that must be considered during migration.

## New overview

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

For frontend validation, run `npm run typecheck` and `npm run build` inside `frontend/`. Recharts is the overview candidate; the broader chart-library trial and matched Streamlit/new-UI latency comparison remain open.

## Current structure

| Path | Purpose |
| --- | --- |
| `app.py`, `pages/` | Existing Streamlit application, retained during migration |
| `app_core/` | Data loading and reusable statistical functions |
| `backend/` | FastAPI overview and coverage endpoints |
| `frontend/` | Next.js overview with shadcn/ui primitives and Recharts |
| `tests/` | Python data, analysis and API tests |
| `data/` | Tracked sample data and geographical boundaries |
| `notebooks/` | Original exploratory research |
| `docs/` | Migration plan and historical documentation |

Existing features will be replaced in verified stages before obsolete UI code is removed.

## Repository provenance

This is an independent continuation of [TaoM29/data-to-descision-dashboard](https://github.com/TaoM29/data-to-descision-dashboard), preserving its Git history from baseline commit `b3dd41d626153cebce2f2945ad1efc0a195d7bd7`. The original repository remains separate.

Development and future pushes belong to [TaoM29/norwegian-energy-dashboard](https://github.com/TaoM29/norwegian-energy-dashboard). The original Streamlit deployment is a reference to the earlier project, not a deployment of the planned Next.js dashboard.

Data sources: [Elhub](https://api.elhub.no/) and [Open-Meteo](https://open-meteo.com/). Dataset attribution and source/model provenance will remain visible in the new application.

## Credential handling and sanitized history

On 2026-09-14, this repository's history was rewritten to remove exposed MongoDB credentials and the previously committed `.streamlit/secrets.toml`. Commit IDs differ from the original repository, whose history was not modified. The baseline hash above identifies the original project's source commit.

The connection cell in `notebooks/part-2.ipynb` now requires `MONGO_URI` in the environment. Streamlit continues to use the ignored local secrets file. Never commit either source of credentials. Run `python scripts/check_secrets.py --history` before pushing; CI runs the same targeted check.

Credential removal does not revoke exposed passwords or remove copies in other repositories. Rotate affected database-user passwords in MongoDB Atlas and update applications using them. After this rewrite, use a fresh clone or carefully reset local branches; do not merge old history back into this repository.
