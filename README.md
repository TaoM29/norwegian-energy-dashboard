
[![CI - Tests](https://github.com/TaoM29/data-to-descision-dashboard/actions/workflows/tests.yml/badge.svg)](https://github.com/TaoM29/data-to-descision-dashboard/actions/workflows/tests.yml) [![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://data-to-descision-dashboard-nonewthing.streamlit.app)


# Dashboards & Data Pipeline

A well-documented **“Data → Decision”** Streamlit dashboard for exploring Norwegian energy (Elhub) and weather (ERA5), with analysis + forecasting modules.

- **Live app:** https://data-to-descision-dashboard-nonewthing.streamlit.app  
- **Repo:** https://github.com/TaoM29/data-to-descision-dashboard  

---

## What this app does
- Interactive exploration of **hourly energy production/consumption (NO1–NO5, 2021–2024)**
- Weather enrichment from **Open-Meteo ERA5**
- Regional **price-area map** (click-to-select coordinates → used by downstream pages)
- Time-series analytics: **STL decomposition** + **spectrogram**
- Data quality: **SPC-style outliers** + **LOF anomalies**
- Forecasting: **SARIMAX** with optional weather exogenous variables
- Model evaluation: **seasonal-naive baseline + rolling-origin backtesting** (MAE/RMSE/MASE)

---

## Tech stack
- **App/UI:** Streamlit, Plotly, Folium (streamlit-folium)
- **Data:** MongoDB (energy), Open-Meteo ERA5 (weather)
- **Modeling/analysis:** statsmodels (STL/SARIMAX), SciPy (spectrogram, DCT), scikit-learn (LOF)
- **Quality:** pytest (unit tests)

---

## Data sources & conventions
- **Energy:** Elhub hourly production/consumption by group and price area (NO1–NO5), 2021–2024 (stored in MongoDB).
- **Weather:** ERA5 hourly data via Open-Meteo Archive API (loaded/cached on demand).
- **Time handling:** weather is requested in `Europe/Oslo`; most analysis pages align series in **UTC** for consistency.
- **Aggregation:** hourly → daily uses **sum** for energy; weather uses **mean** (temp/wind) and **sum** (precipitation).

---

## Repository structure
- `app.py` — Streamlit entry point (multi-page app)
- `pages/` — Streamlit pages (exploration, map, modelling, diagnostics)
- `app_core/` — reusable loaders + analysis utilities (keeps pages thin)
- `data/` — project data used by notebooks and the app
- `notebooks/` — Jupyter notebooks for each project part
- `tests/` — unit tests for key analysis/loader functions
- `requirements.txt` — Python dependencies

---

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Run tests
```bash
pytest -q
```

> Tip: run commands from the repo root; restart/refresh Streamlit if the UI looks stale.
