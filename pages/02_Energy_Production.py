
# pages/02_Energy_Production.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse


# Page config + quick cache reset
st.set_page_config(page_title="Elhub – Energy Production", layout="wide")
st.title("Elhub – Energy Production")

col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("Reset caches"):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.success("All caches cleared — press Rerun")


# Consistent colors per production group (used by BOTH pie and line plots)
GROUP_COLORS = {
    "hydro":   "#4E79A7",  # blue
    "wind":    "#59A14F",  # green
    "solar":   "#EDC948",  # yellow
    "thermal": "#E15759",  # red
    "nuclear": "#B07AA1",  # purple
    "other":   "#BAB0AC",  # gray
}
def _colors_for(labels):
    return [GROUP_COLORS.get(x, "#999999") for x in labels]


# Mongo helpers
def _ensure_auth_source(uri: str) -> str:
    """Add/ensure authSource=admin + safe defaults."""
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


# Collections & control data (areas/groups rarely change, fetch once)
db = get_db()
hour = db["prod_hour"]
year = db["prod_year_totals"]

@st.cache_data(ttl=3600, show_spinner=False)
def _distinct_values():
    return sorted(hour.distinct("price_area")), sorted(hour.distinct("production_group"))

areas, groups_all = _distinct_values()
months = pd.period_range("2021-01", "2021-12", freq="M")
month_labels = [m.strftime("%Y-%m") for m in months]

PAGE = "p4"  # unique key prefix for this page


# Cached data fetchers
@st.cache_data(ttl=600, show_spinner=False)
def get_year_totals_df(price_area: str) -> pd.DataFrame:
    """Return yearly totals for a price area as a DataFrame (cached)."""
    totals = list(year.find({"price_area": price_area}, {"_id": 0}))
    if not totals:
        pipeline = [
            {"$match": {"price_area": price_area}},
            {"$group": {"_id": "$production_group", "total_kwh_2021": {"$sum": "$quantity_kwh"}}},
            {"$project": {"production_group": "$_id", "total_kwh_2021": 1, "_id": 0}},
            {"$sort": {"total_kwh_2021": -1}},
        ]
        totals = list(hour.aggregate(pipeline))
    return pd.DataFrame(totals)

@st.cache_data(ttl=600, show_spinner=False)
def get_hourly_df(price_area: str, year_: int, month_: int, groups: tuple[str, ...]) -> pd.DataFrame:
    """Return hourly rows matching filters as a DataFrame (cached)."""
    start = pd.Timestamp(year=year_, month=month_, day=1, tz="UTC")
    end = (start + pd.offsets.MonthEnd(1)).to_pydatetime()

    query = {"price_area": price_area, "start_time": {"$gte": start.to_pydatetime(), "$lte": end}}
    if groups:
        query["production_group"] = {"$in": list(groups)}  # Mongo expects list

    rows = list(hour.find(query, {"_id": 0, "production_group": 1, "start_time": 1, "quantity_kwh": 1}))
    if not rows:
        return pd.DataFrame(columns=["production_group", "start_time", "quantity_kwh"])
    df_hour = pd.DataFrame(rows)
    df_hour["start_time"] = pd.to_datetime(df_hour["start_time"], utc=True)
    return df_hour


# UI
st.subheader("Production by Area & Group (2021)")
left, right = st.columns(2)

# LEFT: radio + pie (yearly totals) 
with left:
    pa = st.radio("Choose price area", areas, index=0, horizontal=True, key=f"{PAGE}_area")

    with st.spinner("Loading yearly totals…"):
        df_tot = get_year_totals_df(pa)

    if df_tot.empty:
        st.info(f"No data available for price area **{pa}**.")
    else:
        labels = df_tot["production_group"].tolist()
        sizes  = df_tot["total_kwh_2021"].tolist()
        colors = _colors_for(labels)

        fig1, ax1 = plt.subplots(figsize=(6, 6))
        # Simple pie + legend (percentages), colors consistent across the app
        ax1.pie(sizes, colors=colors, startangle=90)
        ax1.set_title(f"Total Production in 2021 – {pa}")
        ax1.axis("equal")

        total = sum(sizes) if sizes else 0
        legend_labels = [f"{g} — {100*s/total:.1f}%" if total else f"{g} — 0.0%"
                         for g, s in zip(labels, sizes)]
        ax1.legend(legend_labels, loc="best", frameon=False)

        st.pyplot(fig1, clear_figure=True)
        plt.close(fig1)

# RIGHT: multiselect + month + line 
with right:
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

    # Cache key wants hashable types → tuple(sorted(...))
    groups_key = tuple(sorted(selected_groups)) if selected_groups else tuple()

    with st.spinner("Loading hourly data…"):
        df_hour = get_hourly_df(pa, y, m, groups_key)

    if df_hour.empty:
        st.info(f"No hourly data for **{pa}** in **{month_label}** with current filters.")
    else:
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

        fig2, ax2 = plt.subplots(figsize=(8, 4))
        for col in pivot.columns:
            ax2.plot(
                pivot.index,
                pivot[col],
                label=col,
                linewidth=1.6,
                color=GROUP_COLORS.get(col, "#999999"),
            )

        ax2.set_title(f"Hourly Production – {pa} – {month_label}")
        ax2.set_xlabel("Time (UTC)")
        ax2.set_ylabel("kWh")
        ax2.legend(title="Group", ncols=2, loc="upper left", frameon=False)
        fig2.tight_layout()
        st.pyplot(fig2, clear_figure=True)
        plt.close(fig2)


# Expander: data source & notes
with st.expander("Data source & notes"):
    st.markdown(
        """
- **Source:** Elhub energy-data API (`PRODUCTION_PER_GROUP_MBA_HOUR`), curated in a Jupyter Notebook.
- **Fields kept:** `priceArea`, `productionGroup`, `startTime` (UTC), `quantityKwh`.
- **Storage:** MongoDB Atlas – database `ind320`  
  • `prod_hour` (hourly curated rows)  
  • `prod_year_totals` (yearly totals per area & group)  
- Caching: database connection is cached as a **resource**; query results are cached as **data** for 10 minutes.
- Credentials are read from **Streamlit secrets**; never hard-coded or read from environment variables.
"""
    )