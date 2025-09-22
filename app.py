import streamlit as st
from data_loader import load_data

st.set_page_config(page_title="IND320 – Project Work (Part 1)", page_icon="📊", layout="wide")

st.title("📊 IND320 — Project Work, Part 1")
st.caption("Use the sidebar to navigate between pages.")

# Sidebar navigation (robust across Streamlit versions)
with st.sidebar:
    st.header("Navigate")
    choice = st.radio(
        "Go to",
        ["Home", "Data Table", "Explorer", "About"],
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("Data is cached for speed.")

# Route based on selection
if choice == "Home":
    df = load_data()
    st.subheader("Quick preview of data")
    st.dataframe(df.head(), use_container_width=True)

elif choice == "Data Table":
    try:
        st.switch_page("pages/02_Data_Table.py")
    except Exception:
        st.warning("Navigation fallback: use the built-in page menu (top-left) to open **Data Table**.")

elif choice == "Explorer":
    try:
        st.switch_page("pages/03_Explorer.py")
    except Exception:
        st.warning("Navigation fallback: use the built-in page menu (top-left) to open **Explorer**.")

elif choice == "About":
    try:
        st.switch_page("pages/04_About.py")
    except Exception:
        st.warning("Navigation fallback: use the built-in page menu (top-left) and open **About**.")





