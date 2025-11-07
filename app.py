
# app.py — minimal entry for multi-page app
import streamlit as st

st.set_page_config(page_title="IND320 – Project App", page_icon="📊", layout="wide")

# Initialize session state variables
st.session_state.setdefault("selected_area", "NO1")
st.session_state.setdefault("selected_year", 2021)

st.markdown("# IND320 – Project App 📊")

st.markdown(
    """
- Use the left sidebar to **navigate** between pages.

- All pages are located under **`pages/`**. The order is controlled by numeric prefixes in filenames (e.g., `01_*.py`, `02_*.py`).

- 🌐 **App (Cloud):** https://ind320-project-work-nonewthing.streamlit.app

- 🧑‍💻 **Repo:** https://github.com/TaoM29/IND320-dashboard-basics
"""
)





