

"""
mongo_loader.py
Tiny helper to read curated Elhub data from MongoDB Atlas.

Requires the environment variable MONGODB_URI to be set (never commit secrets).
Example (local shell):
    export MONGODB_URI='mongodb+srv://<user>:<pass>@<cluster>/?retryWrites=true&w=majority&appName=<app>'

Streamlit Cloud:
- Add MONGODB_URI under Settings → Secrets.
"""

from typing import Optional
from datetime import datetime
import os
import pandas as pd
from pymongo import MongoClient

def load_curated_mongo(
    db_name: str = "ind320",
    collection: str = "elhub_curated",
    meter_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """Load curated docs from MongoDB and return a pandas DataFrame."""
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set. Export it locally or add to Streamlit secrets.")
    client = MongoClient(uri)
    try:
        col = client[db_name][collection]
        query = {}
        if meter_id:
            query["meter_id"] = meter_id
        if start or end:
            query["time"] = {}
            if start:
                query["time"]["$gte"] = start
            if end:
                query["time"]["$lte"] = end

        cursor = col.find(query).sort("time", 1)
        if limit:
            cursor = cursor.limit(int(limit))

        docs = list(cursor)
        if not docs:
            return pd.DataFrame(columns=["meter_id","time","quantity","unit","quality"])

        df = pd.DataFrame(docs)
        # Normalize/clean fields
        if "_id" in df.columns:
            df = df.drop(columns=["_id"])
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
        return df
    finally:
        client.close()
