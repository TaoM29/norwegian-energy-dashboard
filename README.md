
# IND320 – Project Work

# IND320 — Dashboard Basics (Part 1)

Minimal, well-documented Streamlit dashboard for the IND320 “Data to Decision” course.  
**Live app:** https://ind320-project-work-nonewthing.streamlit.app  
**Repo:** https://github.com/TaoM29/IND320-dashboard-basics

---

## What this repo contains
- `app.py` — self-contained Streamlit app with **four pages** (Home, Data Table, Explorer, About) via a sidebar radio.
- `data_loader.py` — cached CSV loader (`@st.cache_data`) used by `app.py`.
- `data/open-meteo-subset.csv` — supplied hourly weather subset (time + 5 variables).
- `part-1.ipynb` — Jupyter notebook: data loading, quick EDA, single-column plots, and all-columns (normalized) plot.
- `requirements.txt` — minimal dependencies (`streamlit`, `pandas`, `matplotlib`).


## How the app works (requirements → implementation)

**Front page & navigation**  
- Sidebar radio provides **Home / Data Table / Explorer / About**.  
- Home shows a small data preview.

**Data loading & caching**  
- `load_data()` in `data_loader.py` reads `data/open-meteo-subset.csv`, parses the `time` column, and caches the DataFrame with `@st.cache_data` to speed up multi-page use.

**Page 2 — Data Table**  
- Shows one **row per variable** (excluding `time`).  
- Columns: `Variable`, `Unit` (parsed from the header e.g. `wind_speed_10m (m/s)` → `m/s`), `Min`, `Mean`, `Max`, and a **LineChartColumn** with the **first calendar month** of that variable’s values (hourly sparkline).

**Page 3 — Explorer**  
- `selectbox` to choose **one column** or **All columns**.  
- `select_slider` to choose a **month range**, default = the **first month** (per assignment).  
- If **All columns**: series are **normalized 0–1** so they can share one y-axis.  
- If **single column**: plotted with unit-aware y-label and proper titles.


## Live app
- https://ind320-project-work-nonewthing.streamlit.app

## GitHub repository
- https://github.com/TaoM29/IND320-dashboard-basics

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
