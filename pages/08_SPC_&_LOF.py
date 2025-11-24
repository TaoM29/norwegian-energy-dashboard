
# pages/08_Quality_Outliers_Anomalies.py
import streamlit as st
from app_core.loaders.weather import load_openmeteo_era5
from app_core.analysis.quality import plot_temperature_outliers_dct, plot_precip_anomalies_lof

st.title("Data Quality — SPC & LOF")

area = st.session_state.get("selected_area", "NO1")
year = st.session_state.get("selected_year", 2021)
df = load_openmeteo_era5(area, int(year))

tabs = st.tabs(["Outlier / SPC (Temperature)", "Anomaly / LOF (Precipitation)"])

with tabs[0]:
    col1, col2 = st.columns(2)
    with col1: cutoff_fraction = st.slider("DCT low-freq keep", 0.01, 0.30, 0.10, 0.01)
    with col2: k_sigma = st.slider("SPC width (k·σ_robust)", 1.0, 5.0, 3.0, 0.1)
    fig, summary, outliers = plot_temperature_outliers_dct(df, cutoff_fraction=float(cutoff_fraction),
                                                           k_sigma=float(k_sigma), title=f"{area} {year} — Temperature Outliers (DCT)")
    st.pyplot(fig); st.subheader("Summary"); st.json(summary)
    st.subheader("Sample outliers"); st.dataframe(outliers.head(30), use_container_width=True)

with tabs[1]:
    col1, col2 = st.columns(2)
    with col1: contamination = st.slider("LOF contamination", 0.001, 0.05, 0.01, 0.001)
    with col2: n_neighbors = st.slider("LOF n_neighbors", 10, 120, 60, 5)
    fig_p, summary_p, anomalies_p = plot_precip_anomalies_lof(df, contamination=float(contamination),
                                                               n_neighbors=int(n_neighbors), title=f"{area} {year} — Precipitation Anomalies (LOF)")
    st.pyplot(fig_p); st.subheader("Summary"); st.json(summary_p)
    st.subheader("Sample anomalies"); st.dataframe(anomalies_p.head(30), use_container_width=True)
