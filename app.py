
# app.py
import os
import streamlit as st

st.set_page_config(page_title="IND320 – Project App", page_icon="📊", layout="wide")

st.markdown("# IND320 – Energy & Weather 📊")
st.caption("Elhub production/consumption (2021–2024) + ERA5 weather.")

# Quick entry points 
home_path = "pages/01_Home.py"
about_path = "pages/99_About.py"

c1, c2 = st.columns(2)

with c1:
    if os.path.exists(home_path):
        st.page_link(home_path, label="Open Home", icon=":material/home:")
    else:
        st.warning("`pages/01_Home.py` not found.")

with c2:
    if about_path:
        st.page_link(about_path, label="Open About", icon=":material/info:")
    else:
        st.warning("`pages/99_About.py` not found.")

st.divider()


# Project links
st.markdown(
    """
**Project links**
- 🌐 App (Cloud): https://ind320-project-work-nonewthing.streamlit.app
- 🧑‍💻 Repo: https://github.com/TaoM29/IND320-dashboard-basics
"""
)





