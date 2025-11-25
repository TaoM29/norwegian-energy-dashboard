
# app.py
import os
import streamlit as st

st.set_page_config(page_title="IND320 – Project App", page_icon="📊", layout="wide")

st.markdown("# IND320 – Energy & Weather 📊")
st.caption("Elhub production/consumption (2021–2024) + ERA5 weather.")

# Only a single call-to-action to open the Home page
home_path = "pages/01_Home.py"
if os.path.exists(home_path):
    st.page_link(home_path, label="Open Home", icon=":material/home:")
else:
    st.warning("Home page not found at `pages/01_Home.py`. Please create it.")


# Helpful links & notes
st.markdown(
    """
**Project links**
- 🌐 App (Cloud): https://ind320-project-work-nonewthing.streamlit.app
- 🧑‍💻 Repo: https://github.com/TaoM29/IND320-dashboard-basics
"""
)





