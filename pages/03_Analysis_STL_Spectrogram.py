
# pages/03_Analysis_STL_Spectrogram.py (NEW A)
import streamlit as st, pandas as pd
from pathlib import Path
from stl_utils import stl_decompose_elhub
from spec_utils import plot_production_spectrogram

st.title("Analysis — STL & Spectrogram")

area = st.session_state.get("selected_area", "NO1")
group = st.selectbox("Production group", ["hydro","wind","solar","thermal","other"], index=2, key="stl_group")
period = st.number_input("STL period (h)", 1, 1000, 24)
seasonal = st.number_input("STL seasonal (odd)", 7, 9999, 13, step=2)
trend = st.number_input("STL trend (odd)", 7, 9999, 365, step=2)
robust = st.checkbox("Robust", True)

tabs = st.tabs(["STL (production)", "Spectrogram (production)"])

csv_path = Path(__file__).resolve().parents[1] / "data" / "elhub_prod_by_group_hour_2021.csv"
df_elhub = pd.read_csv(csv_path, parse_dates=["start_time"])

with tabs[0]:
    figs, details, _ = stl_decompose_elhub(df_elhub, area=area, group=group,
                                           period=int(period), seasonal=int(seasonal), trend=int(trend), robust=bool(robust))
    st.json(details)
    for k in ["observed","seasonal","trend","resid"]:
        st.pyplot(figs[k])

with tabs[1]:
    win = st.number_input("Window length (h)", 8, 2000, 168)
    ovl = st.number_input("Overlap (h)", 0, 1999, 84)
    fig_sp, *_ = plot_production_spectrogram(df_elhub, area=area, group=group, window_len=int(win), overlap=int(ovl))
    st.pyplot(fig_sp)
