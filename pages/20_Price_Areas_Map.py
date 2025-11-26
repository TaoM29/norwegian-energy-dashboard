
# pages/20_Map_Price_Areas.py
from __future__ import annotations

import json, re, glob
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

import pandas as pd
import streamlit as st

# Folium + Streamlit bridge
try:
    import folium
    from streamlit_folium import st_folium
    import branca.colormap as cm
except Exception:
    st.error(
        "This page needs extra packages: **folium**, **streamlit-folium**, **branca**.\n"
        "Add them to `requirements.txt`, reinstall your env, and rerun."
    )
    st.stop()

from app_core.loaders.mongo_utils import get_db


# Basic page setup
st.set_page_config(page_title="Map of Price Areas", layout="wide")
st.title("Map — Price Areas & Aggregates")

SELECTED_AREA = st.session_state.get("selected_area", "NO1")
st.caption(f"Active price area: **{SELECTED_AREA}** (set on “02 · Price Area Selector”)")

db = get_db()


# GeoJSON helpers
def canonical_area(value: str) -> str | None:
    """
    Normalize many variants to 'NO1'..'NO5'.
    Accepts: 'NO1', 'no1', 'NO 1', 'NO-1', 'NO1 – Østlandet', etc.
    """
    if not isinstance(value, str):
        return None
    m = re.search(r"NO\s*[- ]?\s*([1-5])", value, flags=re.IGNORECASE)
    return f"NO{m.group(1)}" if m else None

def list_local_geojson_files() -> List[str]:
    return sorted(glob.glob("data/*.geojson"))

def load_geojson(path: str) -> Dict[str, Any]:
    # Handle UTF-8 BOM if present
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def detect_area_field(gj: Dict[str, Any]) -> Tuple[str | None, List[str]]:
    """
    Try to find which property holds NO1..NO5 codes.
    Returns: (field_name | None, list_of_detected_areas)
    """
    features = gj.get("features", [])
    if not features:
        return None, []

    score: Dict[str, int] = {}
    # Look at up to first 200 features to score candidate keys
    for feat in features[:200]:
        props = feat.get("properties", {}) or {}
        for k, v in props.items():
            if canonical_area(str(v)):
                score[k] = score.get(k, 0) + 1

    if not score:
        return None, []

    field = max(score, key=score.get)
    areas = sorted({
        canonical_area(str(f.get("properties", {}).get(field, "")))
        for f in features
        if canonical_area(str(f.get("properties", {}).get(field, "")))
    })
    return field, areas


# Sidebar: choose GeoJSON
with st.sidebar:
    st.header("GeoJSON")
    files = list_local_geojson_files()
    if not files:
        st.error("Put your exported **.geojson** under the `data/` folder.")
        st.stop()

    default_path = st.session_state.get("map_geojson_path", files[0])
    gj_path = st.selectbox("Choose GeoJSON", files, index=files.index(default_path) if default_path in files else 0)
    st.session_state["map_geojson_path"] = gj_path

GEOJSON = load_geojson(gj_path)
AREA_FIELD, AREAS = detect_area_field(GEOJSON)

if not AREA_FIELD or not AREAS:
    st.error(
        "Could not detect a GeoJSON property that contains NO1–NO5 area codes.\n"
        "Please export the *Elspot areas* layer and place it under `data/`."
    )
    st.stop()

st.caption(f"Detected GeoJSON field for price-area code: **{AREA_FIELD}**")



# Controls
colA, colB, colC, colD = st.columns([1.2, 1.2, 1, 2])

with colA:
    kind = st.radio("Data source", ["Production", "Consumption"], horizontal=True)

with colB:
    if kind == "Production":
        groups = ["hydro", "wind", "solar", "thermal", "nuclear", "other"]
        grp = st.selectbox("Group", groups, index=2)
    else:
        groups = ["household", "cabin", "primary", "secondary", "tertiary", "industry", "private", "business"]
        grp = st.selectbox("Group", groups, index=0)

with colC:
    days = st.slider("Interval (days)", 1, 365, 30)

with colD:
    end_default = datetime(2024, 12, 31, 23, 59, 59)
    end_date = st.date_input("End date (UTC)", value=end_default.date())
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    start_dt = end_dt - timedelta(days=days - 1)
    st.caption(f"Period: **{start_dt:%Y-%m-%d} → {end_dt:%Y-%m-%d}**")



# Mongo aggregation
def _agg_mean(coll_name: str, group_field: str, group_value: str,
              start: datetime, end: datetime) -> pd.DataFrame:
    pipe = [
        {"$match": {
            "price_area": {"$in": AREAS},
            group_field: group_value,
            "start_time": {"$gte": start, "$lte": end},
        }},
        {"$group": {"_id": "$price_area", "mean_kwh": {"$avg": "$quantity_kwh"}}},
        {"$project": {"_id": 0, "price_area": "$_id", "mean_kwh": 1}},
    ]
    rows = list(db[coll_name].aggregate(pipe, allowDiskUse=True))
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["price_area", "mean_kwh"])

def mean_by_area(kind: str, group: str, start: datetime, end: datetime) -> pd.DataFrame:
    if kind == "Production":
        df21 = _agg_mean("prod_hour", "production_group", group, start, end)
        df24 = _agg_mean("elhub_production_mba_hour", "production_group", group, start, end)
        df = pd.concat([df21, df24], ignore_index=True)
        return df.groupby("price_area", as_index=False)["mean_kwh"].mean() if not df.empty else df
    return _agg_mean("elhub_consumption_mba_hour", "consumption_group", group, start, end)

with st.spinner("Querying MongoDB for mean kWh…"):
    df_mean = mean_by_area(kind, grp, start_dt, end_dt)

if df_mean.empty:
    st.info("No rows for the chosen interval/group. Try another period or group.")
    st.stop()

# Map value dict & color scale
val_map = {r["price_area"]: float(r["mean_kwh"]) for _, r in df_mean.iterrows()}
vmin, vmax = min(val_map.values()), max(val_map.values())
if vmin == vmax:
    vmax = vmin + 1.0
cmap = cm.linear.YlOrRd_09.scale(vmin, vmax)
cmap.caption = f"Mean kWh ({kind.lower()} • {grp})"



# Folium map
m = folium.Map(location=[65.0, 13.5], zoom_start=4.6, tiles="cartodbpositron")

def style_fn(feature):
    raw = feature.get("properties", {}).get(AREA_FIELD, "")
    code = canonical_area(str(raw))
    val = val_map.get(code)
    return {
        "fillColor": cmap(val) if val is not None else "#dddddd",
        "color": "#000000" if code == SELECTED_AREA else "#333333",
        "weight": 3 if code == SELECTED_AREA else 1.5,
        "fillOpacity": 0.45 if val is not None else 0.15,
    }

folium.GeoJson(
    data=GEOJSON,
    name="Price Areas",
    style_function=style_fn,
    tooltip=folium.GeoJsonTooltip(fields=[AREA_FIELD], aliases=["Area"], sticky=False, labels=True),
).add_to(m)

cmap.add_to(m)

# keep last clicked marker
if "clicked_coord" in st.session_state:
    lat, lon = st.session_state["clicked_coord"]
    folium.CircleMarker((lat, lon), radius=5, color="#0B6E4F", fill=True, fill_opacity=0.9,
                        tooltip=f"Clicked: {lat:.4f}, {lon:.4f}").add_to(m)

out = st_folium(m, height=620, use_container_width=True)


if out and out.get("last_clicked"):
    lat = out["last_clicked"]["lat"]
    lon = out["last_clicked"]["lng"]
    st.session_state["clicked_coord"] = (lat, lon)
    st.success(f"Saved click: **({lat:.5f}, {lon:.5f})**")


# Hand-off to Snow Drift
if "clicked_coord" in st.session_state:
    lat, lon = st.session_state["clicked_coord"]
    st.caption("Next: compute snow drift for the clicked point")
    st.page_link(
        "pages/21_Snow_Drift.py",
        label=f"Go to Snow Drift (Tabler) for ({lat:.5f}, {lon:.5f})",
        icon=":material/ac_unit:"
    )
else:
    st.info(
        "Tip: Click anywhere on the map to choose a coordinate. "
        "Then you can open the **Snow Drift** page to compute drift for that point.",
        icon="🧭",
    )

# Table
st.subheader("Mean kWh per price area (selected interval)")
st.dataframe(
    df_mean.sort_values("price_area").assign(mean_kwh=lambda d: d["mean_kwh"].round(2)),
    hide_index=True, use_container_width=True
)


