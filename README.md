# Dashboards & Data Pipeline

Minimal, well-documented Streamlit dashboard for the IND320 “Data to Decision” course.  
**Live app:** https://ind320-project-work-nonewthing.streamlit.app  
**Repo:** https://github.com/TaoM29/IND320-dashboard-basics

---

## What this repo contains
- `app.py` — self-contained Streamlit app with **four pages** (Home, Data Table, Explorer, About) via a sidebar radio.
- `data_loader.py` — cached CSV loader (`@st.cache_data`) used by `app.py`.
- `mongo_loader.py` — helper utilities for uploading data to MongoDB (reads connection info from env/secrets).
- `part-1.ipynb` — Jupyter notebook: data loading, quick EDA, single-column plots, and all-columns (normalized) plot.
- `part-2.ipynb` — Jupyter notebook for 2021 energy production: build the full dataset month-by-month (per API window), run a quick coherence check, export CSV for the app, and optionally insert into MongoDB.
- `requirements.txt` — minimal dependencies (`streamlit`, `pandas`, `matplotlib`, `pymongo`, `certifi`).
- `data/` — project CSVs used by notebooks and the app.
- `pages/` — extra Streamlit pages (e.g., Part-2 page).
- `pdf/` — exported notebook PDFs.

---

## App navigation
The sidebar has two sections:
- **app** (Part 1): *Home*, *Data Table*, *Explorer*, *About* — weather data quick EDA with cached CSVs.
- **energy production** (Part 2): a dedicated page for Elhub production data (2021).

---

## Part 2 — Energy production (2021)
- **Controls:** choose **price area** (NO1–NO5), toggle **production groups**, and pick a **month**.
- **Charts:** **Pie** (total production share in 2021) and **Line** (hourly production for the selected month).  
- **Notes:** data loaded from CSV (and optionally MongoDB); plots use a simple, readable style with fixed colors per group.

---

## MongoDB upload
**File:** `mongo_loader.py`  
**Requires secrets:** `MONGO_URI`, `MONGO_DB`, `MONGO_COLLECTION` (set via environment variables or Streamlit Secrets).

**Recommended flow**
1. Build/clean your DataFrame in the notebook.  
2. Run the coherence check cell.  
3. Insert into Mongo **only after** the checks pass.

---

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py

If you see import or cache issues, run from the repo root and click Rerun in Streamlit.
For Streamlit Cloud, mirror your local secrets (Mongo, etc.) in the app’s Secrets.

