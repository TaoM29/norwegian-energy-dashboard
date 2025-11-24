
# pages/99_Debug_Mongo.py
import streamlit as st
from app_core.loaders.mongo_utils import get_db

st.set_page_config(page_title="Debug Mongo", layout="wide")
st.title("Debug Mongo")

db = get_db()
st.write("prod 2022–2024:", db["elhub_production_mba_hour"].estimated_document_count())
st.write("cons 2021–2024:", db["elhub_consumption_mba_hour"].estimated_document_count())
st.write("prod 2021 (old):", db["prod_hour"].estimated_document_count())