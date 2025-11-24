# app_core/loaders/mongo_utils.py
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import streamlit as st

# collection names (consistent with your notebook writes)
COLL_PROD_2021 = "prod_hour"                       # 2021 production
COLL_PROD_2224 = "elhub_production_mba_hour"       # 2022–2024 production
COLL_CONS_2124 = "elhub_consumption_mba_hour"      # 2021–2024 consumption
COLL_PROD_TOTALS_2021 = "prod_year_totals"         # legacy (2021 totals only)

def _ensure_auth_source(uri: str) -> str:
    p = urlparse(uri)
    q = dict(parse_qsl(p.query))
    q.setdefault("authSource", "admin")
    q.setdefault("retryWrites", "true")
    q.setdefault("w", "majority")
    q.setdefault("appName", "Cluster007")
    new_q = urlencode(q)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))

@st.cache_resource
def get_db():
    uri = st.secrets["MONGO_URI"].strip()
    dbname = st.secrets.get("MONGO_DB", "ind320")
    uri = _ensure_auth_source(uri)
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    return client[dbname]

def get_prod_coll_for_year(year: int):
    db = get_db()
    return db[COLL_PROD_2021] if year == 2021 else db[COLL_PROD_2224]

def get_cons_coll():
    return get_db()[COLL_CONS_2124]