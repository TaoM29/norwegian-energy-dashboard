
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="IND320 – Dashboard Basics", page_icon="📊", layout="centered")

st.title("📊 IND320: Minimum Working App")
st.caption("Deployed from GitHub • Streamlit Cloud")

# Tiny dataset
df = pd.DataFrame({
    "category": ["A", "B", "C", "D"],
    "value": [12, 7, 19, 4]
})

st.subheader("Data preview")
st.dataframe(df, use_container_width=True)

st.subheader("Pick a category")
choice = st.selectbox("Category", df["category"])

st.subheader("Bar chart")
fig, ax = plt.subplots()
ax.bar(df["category"], df["value"])
ax.set_xlabel("Category")
ax.set_ylabel("Value")
st.pyplot(fig)

st.success(f"You selected: {choice}")



