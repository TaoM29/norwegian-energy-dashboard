
# Dashboards & Data Pipeline

Well-documented "Data to Decision" Streamlit dashboard
- **Live app:** https://data-to-descision-dashboard-nonewthing.streamlit.app
- **Repo:** https://github.com/TaoM29/data-to-descision-dashboard

---

## What this repo contains
- `app_core`- folder with relevant loaders and analysis tools.
- `data/` — project data used by notebooks and the app.
- `notebooks/` — jupyter notebooks for each project part.
- `pages/` - different pages for different parts of the project.
- `app.py` — self-contained Streamlit app with pages/ contents.
- `requirements.txt` —  library dependencies for this project.




## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

If you see import or cache issues, run from the repo root and click Rerun in Streamlit.

