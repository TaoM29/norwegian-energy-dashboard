# pages/energy_production.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

st.set_page_config(page_title="Elhub – Energy Production", layout="wide")
st.title("Elhub – Energy Production")

# ---- Mongo helpers ----------------------------------------------------------
def _ensure_auth_source(uri: str) -> str:
    """Add/ensure authSource=admin + some safe defaults."""
    p = urlparse(uri)
    q = dict(parse_qsl(p.query))
    q.setdefault("authSource", "admin")
    q.setdefault("retryWrites", "true")
    q.setdefault("w", "majority")
    q.setdefault("appName", "Cluster007")
    new_q = urlencode(q)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))

def _mask(uri: str) -> str:
    """Mask password in any debug/error output."""
    try:
        p = urlparse(uri)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname}"
            if p.port:
                netloc += f":{p.port}"
            return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        pass
    return uri

@st.cache_resource
def get_db():
    # Only read from Streamlit secrets (avoid ENV overrides)
    uri = st.secrets.get("MONGO_URI", "").strip()
    if not uri:
        raise RuntimeError("MONGO_URI is missing in st.secrets")

    uri = _ensure_auth_source(uri)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        _ = client.server_info()      # forces connect & auth
        client.admin.command("ping")  # explicit ping
        return client[st.secrets.get("MONGO_DB", "ind320")]
    except PyMongoError as e:
        st.error(f"Mongo auth/connect failed. URI: {_mask(uri)}\n{e}")
        raise

# ---- Collections ------------------------------------------------------------
db = get_db()
hour = db["prod_hour"]
year = db["prod_year_totals"]

# ---- Controls data ----------------------------------------------------------
areas = sorted(hour.distinct("price_area"))
groups_all = sorted(hour.distinct("production_group"))
months = pd.period_range("2021-01", "2021-12", freq="M")
month_labels = [m.strftime("%Y-%m") for m in months]

PAGE = "p4"  # unique key prefix for this page

st.subheader("Production by Area & Group (2021)")
left, right = st.columns(2)

# ---------------------- LEFT: radio + pie (yearly totals) --------------------
with left:
    pa = st.radio("Choose price area", areas, index=0, horizontal=True, key=f"{PAGE}_area")

    # Prefer pre-aggregated totals; fallback to on-the-fly aggregation
    totals = list(year.find({"price_area": pa}, {"_id": 0}))
    if not totals:
        pipeline = [
            {"$match": {"price_area": pa}},
            {"$group": {"_id": "$production_group", "total_kwh_2021": {"$sum": "$quantity_kwh"}}},
            {"$project": {"production_group": "$_id", "total_kwh_2021": 1, "_id": 0}},
            {"$sort": {"total_kwh_2021": -1}},
        ]
        totals = list(hour.aggregate(pipeline))

    df_tot = pd.DataFrame(totals)
    if df_tot.empty:
        st.info(f"No data available for price area **{pa}**.")
    else:
        fig1, ax1 = plt.subplots()
        ax1.pie(df_tot["total_kwh_2021"], labels=df_tot["production_group"],
                autopct="%1.1f%%", startangle=90)
        ax1.set_title(f"Total Production in 2021 – {pa}")
        ax1.axis("equal")
        st.pyplot(fig1, clear_figure=True)
        plt.close(fig1)

# ---------------- RIGHT: pills/multiselect + month + line (hourly) -----------
with right:
    # st.pills if available; else fallback to multiselect
    try:
        selected_groups = st.pills(
            "Production groups",
            groups_all,
            selection_mode="multi",
            default=groups_all,
            key=f"{PAGE}_groups",
        )
    except Exception:
        selected_groups = st.multiselect(
            "Production groups", groups_all, default=groups_all, key=f"{PAGE}_groups"
        )

    month_label = st.selectbox("Month", month_labels, index=0, key=f"{PAGE}_month")
    y = int(month_label[:4]); m = int(month_label[5:7])
    start = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
    end = (start + pd.offsets.MonthEnd(1)).to_pydatetime()

    query = {"price_area": pa, "start_time": {"$gte": start.to_pydatetime(), "$lte": end}}
    if selected_groups:
        query["production_group"] = {"$in": selected_groups}

    rows = list(hour.find(
        query, {"_id": 0, "production_group": 1, "start_time": 1, "quantity_kwh": 1}
    ))

    if not rows:
        st.info(f"No hourly data for **{pa}** in **{month_label}** with current filters.")
    else:
        df_hour = pd.DataFrame(rows)
        df_hour["start_time"] = pd.to_datetime(df_hour["start_time"], utc=True)
        pivot = (
            df_hour.pivot_table(
                index="start_time",
                columns="production_group",
                values="quantity_kwh",
                aggfunc="sum",
            )
            .sort_index()
        )
        if selected_groups:
            pivot = pivot[[c for c in pivot.columns if c in selected_groups]]

        fig2, ax2 = plt.subplots()
        for col in pivot.columns:
            ax2.plot(pivot.index, pivot[col], label=col)
        ax2.set_title(f"Hourly Production – {pa} – {month_label}")
        ax2.set_xlabel("Time (UTC)")
        ax2.set_ylabel("kWh")
        ax2.legend(ncols=2, loc="upper left")
        plt.tight_layout()
        st.pyplot(fig2, clear_figure=True)
        plt.close(fig2)

# ----------------------------- Expander --------------------------------------
with st.expander("Data source & notes"):
    st.markdown(
        """
- **Source:** Elhub energy-data API (`PRODUCTION_PER_GROUP_MBA_HOUR`), curated in a Jupyter Notebook.
- **Fields kept:** `priceArea`, `productionGroup`, `startTime` (UTC), `quantityKwh`.
- **Storage:** MongoDB Atlas – database `ind320`  
  • `prod_hour` (hourly curated rows)  
  • `prod_year_totals` (yearly totals per area & group)  
- Credentials are read from **Streamlit secrets**; never hard-coded or read from environment variables.
"""
    )

