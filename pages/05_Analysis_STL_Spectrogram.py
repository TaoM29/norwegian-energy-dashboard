
# pages/05_Analysis_STL_Spectrogram.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from app_core.analysis.stl import stl_decompose_elhub
from app_core.analysis.spectrogram import production_spectrogram

from app_core.loaders.mongo_utils import get_db, get_prod_coll_for_year

st.set_page_config(page_title="Analysis — STL & Spectrogram", layout="wide")
st.title("Analysis — STL & Spectrogram (Production)")

# Quick cache reset (handy while iterating)
col_reset, _ = st.columns([1, 5])
with col_reset:
    if st.button("Reset caches"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success("Caches cleared — press ⌘/Ctrl+Rerun")

@st.cache_resource
def _db():
    return get_db()

db = _db()

@st.cache_data(ttl=1800, show_spinner=False)
def _areas_groups():
    """Union of distinct areas/groups across years (covers full span)."""
    c21 = None
    c24 = None
    try:
        c21 = get_prod_coll_for_year(2021)
    except Exception:
        pass
    try:
        c24 = get_prod_coll_for_year(2024)
    except Exception:
        pass

    areas, groups = set(), set()

    if c21 is not None:
        areas.update(a for a in c21.distinct("price_area") if a)
        groups.update(g for g in c21.distinct("production_group") if g)
    if c24 is not None:
        areas.update(a for a in c24.distinct("price_area") if a)
        groups.update(g for g in c24.distinct("production_group") if g)

    areas = sorted(areas) or ["NO1", "NO2", "NO3", "NO4", "NO5"]
    groups = sorted(groups) or ["hydro", "wind", "solar", "thermal", "nuclear", "other"]
    return areas, groups

AREAS, GROUPS = _areas_groups()

def _to_dt(d: date, end=False) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59) if end else datetime(d.year, d.month, d.day, 0, 0, 0)

@st.cache_data(ttl=900, show_spinner=True)
def load_prod_range(area: str, group: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    """Load hourly production rows for [area, group, start_dt..end_dt] across multiple year collections."""
    years = list(range(start_dt.year, end_dt.year + 1))
    rows = []
    for yr in years:
        coll = get_prod_coll_for_year(yr)  # returns a Collection
        q = {
            "price_area": area,
            "production_group": group,
            "start_time": {"$gte": start_dt, "$lte": end_dt},
        }
        proj = {"_id": 0, "price_area": 1, "production_group": 1, "start_time": 1, "quantity_kwh": 1}
        rows.extend(list(coll.find(q, proj)))

    if not rows:
        return pd.DataFrame(columns=["price_area", "production_group", "start_time", "quantity_kwh"])

    df = pd.DataFrame(rows)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True, errors="coerce")
    df["quantity_kwh"] = pd.to_numeric(df["quantity_kwh"], errors="coerce")
    df = df.dropna(subset=["start_time"]).sort_values("start_time").reset_index(drop=True)
    return df

# ---------- UI ----------
left, right = st.columns([1.1, 1.9])

with left:
    st.subheader("Selection")
    area = st.selectbox("Price area", AREAS, index=AREAS.index(st.session_state.get("selected_area", AREAS[0])))
    group = st.selectbox("Production group", GROUPS, index=(GROUPS.index("solar") if "solar" in GROUPS else 0))

    default_start = date(2022, 1, 1)
    default_end   = date(2022, 3, 31)
    date_range = st.date_input(
        "Date range (UTC)",
        value=(default_start, default_end),
        min_value=date(2021, 1, 1),
        max_value=date(2024, 12, 31)
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_dt = _to_dt(date_range[0], end=False)
        end_dt   = _to_dt(date_range[1], end=True)
    else:
        start_dt = _to_dt(date_range, end=False)  # type: ignore[arg-type]
        end_dt   = _to_dt(date_range, end=True)   # type: ignore[arg-type]

    st.session_state["selected_area"] = area

    st.markdown("---")
    st.caption("STL parameters")
    c1, c2 = st.columns(2)
    with c1:
        period = st.number_input("Period (hours)", 1, 2000, 24, step=1)
        seasonal = st.number_input("Seasonal (odd)", 7, 9999, 13, step=2)
    with c2:
        trend = st.number_input("Trend (odd)", 7, 9999, 365, step=2)
        robust = st.checkbox("Robust", True)

    st.markdown("---")
    st.caption("Spectrogram parameters")
    c3, c4 = st.columns(2)
    with c3:
        window_len = st.number_input("Window length (hours)", 8, 2000, 168, step=1)
    with c4:
        overlap = st.number_input("Overlap (hours)", 0, 1999, 84, step=1)

with right:
    st.subheader("Data preview")
    with st.spinner("Loading production rows from Mongo…"):
        df = load_prod_range(area, group, start_dt, end_dt)

    st.write(
        f"Rows loaded: **{len(df):,}**  |  "
        f"span: {df['start_time'].min() if not df.empty else '–'} → "
        f"{df['start_time'].max() if not df.empty else '–'}"
    )
    st.dataframe(df.head(20), use_container_width=True)

    if df.empty:
        st.info("No data for the chosen filters. Try a different group or date range.")
    else:
        tabs = st.tabs(["STL (Plotly)", "Spectrogram (Plotly)"])

        with tabs[0]:
            figs, details, _ = stl_decompose_elhub(
                df,
                area=area,
                group=group,
                period=int(period),
                seasonal=int(seasonal),
                trend=int(trend),
                robust=bool(robust),
                time_col="start_time",
                area_col="price_area",
                group_col="production_group",
                value_col="quantity_kwh",
            )
            st.json(details)
            for key in ["observed", "seasonal", "trend", "resid"]:
                if key in figs:
                    st.plotly_chart(figs[key], use_container_width=True)

        with tabs[1]:
            fig_sp, *_ = production_spectrogram(
                df,
                area=area,
                group=group,
                window_len=int(window_len),
                overlap=int(overlap),
                time_col="start_time",
                area_col="price_area",
                group_col="production_group",
                value_col="quantity_kwh",
            )
            st.plotly_chart(fig_sp, use_container_width=True)

with st.expander("Data source & notes"):
    st.markdown(
        """
- **Source:** Elhub `PRODUCTION_PER_GROUP_MBA_HOUR` (curated to Mongo in Part 4).
- **Collections:** `prod_hour` (2021) and `elhub_production_mba_hour` (2022–2024).
- Queries and transformations are cached via `@st.cache_data`.
"""
    )
