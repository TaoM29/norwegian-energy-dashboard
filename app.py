
import streamlit as st
from data_loader import load_data

st.set_page_config(page_title="IND320 – Project Work (Part 1)", page_icon="📊", layout="wide")

st.title("📊 IND320 — Project Work, Part 1")
st.caption("Use the sidebar to navigate between pages.")

# Sidebar navigation
with st.sidebar:
    st.header("Navigate")
    st.page_link("app.py", label="Home", icon="🏠")
    st.page_link("pages/02_Data_Table.py", label="Data Table", icon="📊")
    st.page_link("pages/03_Explorer.py", label="Explorer", icon="📈")
    st.page_link("pages/04_About.py", label="About", icon="ℹ️")
    st.markdown("---")
    st.caption("Data is cached for speed.")

# Quick data preview
df = load_data()
st.subheader("Quick preview of data")
st.dataframe(df.head(), use_container_width=True)




