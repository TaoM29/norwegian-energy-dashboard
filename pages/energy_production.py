import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pymongo import MongoClient

st.set_page_config(page_title="Elhub – Energy Production", layout="wide")
st.title("Elhub – Enery Production")

st.set_page_config(page_title="Page 4 – Production (2021)", layout="wide")

# ---- Secrets / Connection (set in .streamlit/secrets.toml or Streamlit Cloud Secrets) ----
MONGO_URI = st.secrets["MONGO_URI"]
MONGO_DB  = st.secrets.get("MONGO_DB", "ind320")
COLL_HOURLY = "prod_hour"
COLL_YEARLY = "prod_year_totals"

@st.cache_resource
def get_db():
    client = MongoClient(MONGO_URI)
    client.admin.command("ping")
    return client[MONGO_DB]

db = get_db()
hour = db[COLL_HOURLY]
year = db[COLL_YEARLY]

# ---- Controls data ----
areas = sorted(hour.distinct("price_area"))
groups_all = sorted(hour.distinct("production_group"))
months = pd.period_range("2021-01", "2021-12", freq="M")

st.title("Production by Area & Group (2021)")

left, right = st.columns(2)

# ===================== LEFT COLUMN: radio + pie =====================
with left:
    pa = st.radio("Choose price area", areas, index=0, horizontal=True)

    # Prefer pre-aggregated totals; fallback to on-the-fly aggregation if missing
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
        fig = plt.figure()
        plt.pie(
            df_tot["total_kwh_2021"],
            labels=df_tot["production_group"],
            autopct="%1.1f%%",
            startangle=90,
        )
        plt.title(f"Total Production in 2021 – {pa}")
        plt.axis("equal")
        st.pyplot(fig)

# ===================== RIGHT COLUMN: pills + month + line =====================
with right:
    # st.pills is new; if not available in your Streamlit version, fall back to multiselect
    try:
        selected_groups = st.pills(
            "Production groups",
            groups_all,
            selection_mode="multi",
            default=groups_all,
        )
    except Exception:
        selected_groups = st.multiselect("Production groups", groups_all, default=groups_all)

    month_label = st.selectbox("Month", [m.strftime("%Y-%m") for m in months], index=0)
    y = int(month_label[:4])
    m = int(month_label[5:7])

    start = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
    end = (start + pd.offsets.MonthEnd(1)).to_pydatetime()

    query = {
        "price_area": pa,
        "start_time": {"$gte": start.to_pydatetime(), "$lte": end},
    }
    if selected_groups:
        query["production_group"] = {"$in": selected_groups}

    rows = list(
        hour.find(
            query,
            {"_id": 0, "production_group": 1, "start_time": 1, "quantity_kwh": 1},
        )
    )

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

        # Keep only chosen groups (safety)
        if selected_groups:
            pivot = pivot[[c for c in pivot.columns if c in selected_groups]]

        fig2 = plt.figure()
        for col in pivot.columns:
            plt.plot(pivot.index, pivot[col], label=col)

        plt.title(f"Hourly Production – {pa} – {month_label}")
        plt.xlabel("Time (UTC)")
        plt.ylabel("kWh")
        plt.legend(ncols=2, loc="upper left")
        plt.tight_layout()
        st.pyplot(fig2)

# ===================== EXPANDER =====================
with st.expander("Data source & notes"):
    st.markdown(
        """
- **Source:** Elhub energy-data API (`PRODUCTION_PER_GROUP_MBA_HOUR`), curated in a Jupyter Notebook.
- **Fields kept:** `priceArea`, `productionGroup`, `startTime` (UTC), `quantityKwh`.
- **Storage:** MongoDB Atlas – database `ind320`, collections:
  - `prod_hour` (hourly curated rows)
  - `prod_year_totals` (yearly totals per area & group)
- This page reads directly from MongoDB using credentials stored in **Streamlit secrets**.
"""
    )
