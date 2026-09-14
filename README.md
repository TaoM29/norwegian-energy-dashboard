# Norwegian Energy Dashboard

A Norwegian energy and weather analysis project evolving into a **Next.js / React frontend with a Python backend**.

**Status:** Repository established and implementation planned. The code currently runs the original Streamlit application. The new frontend, API, automated data updates, and additional models have not been implemented yet.

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

The inherited application uses Streamlit, Plotly, MongoDB, Open-Meteo, statsmodels, SciPy and scikit-learn. Its existing date selectors target 2021–2024; newer coverage is planned and is not yet loaded by this migration.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Energy pages require local MongoDB configuration in `.streamlit/secrets.toml` (`MONGO_URI`, optionally `MONGO_DB`). Credentials are not included in this repository. Weather requests require network access. See the [preserved original README](docs/LEGACY_README.md) for the inherited project's documentation and original deployment links.

Run the existing Python tests from the repository root:

```bash
python -m pytest -q
```

## Current structure

| Path | Purpose |
| --- | --- |
| `app.py`, `pages/` | Existing Streamlit application, retained during migration |
| `app_core/` | Data loading and reusable statistical functions |
| `tests/` | Existing Python tests |
| `data/` | Tracked sample data and geographical boundaries |
| `notebooks/` | Original exploratory research |
| `docs/` | Migration plan and historical documentation |

The frontend and backend directories will be introduced during implementation. Existing features will be replaced in verified stages before obsolete UI code is removed.

## Repository provenance

This is an independent continuation of [TaoM29/data-to-descision-dashboard](https://github.com/TaoM29/data-to-descision-dashboard), preserving its Git history from baseline commit `b3dd41d626153cebce2f2945ad1efc0a195d7bd7`. The original repository remains separate.

Development and future pushes belong to [TaoM29/norwegian-energy-dashboard](https://github.com/TaoM29/norwegian-energy-dashboard). The original Streamlit deployment is a reference to the earlier project, not a deployment of the planned Next.js dashboard.

Data sources: [Elhub](https://api.elhub.no/) and [Open-Meteo](https://open-meteo.com/). Dataset attribution and source/model provenance will remain visible in the new application.
