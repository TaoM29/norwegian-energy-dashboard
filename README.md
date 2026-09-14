# Norwegian Energy Dashboard

A Norwegian energy and weather analysis project evolving into a **Next.js / React frontend with a Python backend**.

**Status:** Phase 0 is complete: the original Streamlit application has a recorded test baseline, control inventory, and representative outputs and timings from tracked inputs. All 49 existing tests pass in the captured Python 3.11 environment. The new frontend, API, automated data updates, and additional models have not been implemented yet.

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

For the exact tested dependencies, setup commands, results and limitations, see the [Phase 0 baseline](docs/BASELINE.md). The [feature-control inventory](docs/FEATURE_CONTROL_INVENTORY.md) records existing controls, exports and page calculations for migration. The [representative output report](docs/REFERENCE_OUTPUTS.md) includes screenshots, complete chart/table snapshots, numerical references and local execution timings; it does not establish live-source coverage or browser latency.

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

## Credential handling and sanitized history

On 2026-09-14, this repository's history was rewritten to remove exposed MongoDB credentials and the previously committed `.streamlit/secrets.toml`. Commit IDs differ from the original repository, whose history was not modified. The baseline hash above identifies the original project's source commit.

The connection cell in `notebooks/part-2.ipynb` now requires `MONGO_URI` in the environment. Streamlit continues to use the ignored local secrets file. Never commit either source of credentials. Run `python scripts/check_secrets.py --history` before pushing; CI runs the same targeted check.

Credential removal does not revoke exposed passwords or remove copies in other repositories. Rotate affected database-user passwords in MongoDB Atlas and update applications using them. After this rewrite, use a fresh clone or carefully reset local branches; do not merge old history back into this repository.
