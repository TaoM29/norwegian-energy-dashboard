# pages/41_SPC_and_LOF_Data_Quality.py
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_core.loaders.weather import load_openmeteo_era5
from app_core.analysis.data_quality import spc_outliers_dct, lof_precip_anomalies


st.title("Data Quality — SPC (Outliers) & LOF (Anomalies)")

st.markdown(
    """
**What this page shows**

This page helps you **check data quality** in the hourly ERA5 weather series for the selected **price area** and **year**.

### 1) SPC-style outliers (Temperature)
- Builds a **smooth trend** using a **DCT low-pass filter** (keeps only the lowest-frequency coefficients).
- Computes residuals (*actual − trend*) and estimates a **robust σ** using **MAD** (median absolute deviation).
- Creates **control limits**: `trend ± k·σᵣ` and flags points outside the band as **outliers**.
- Also reports **SATV** (*standardized actual-to-trend value*):  
  `SATV = (actual − trend) / σᵣ`  
  Large `|SATV|` means a point is far from the trend in “robust standard deviations”.

**Controls**
- *Keep low-frequency fraction (DCT)*: smaller → smoother trend (captures only slow changes).  
- *SPC width (k·σᵣ)*: larger → wider band → fewer outliers.

### 2) LOF anomalies (Precipitation)
- Uses **Local Outlier Factor (LOF)** to find unusual precipitation behavior.
- Builds a simple 2D feature space:
  - current precipitation value `p(t)`
  - **24h rolling mean** `mean₍24h₎(t)`
- LOF marks points that are **locally rare** compared to their neighborhood as **anomalies**.

**Controls**
- *Contamination*: expected fraction of anomalies (higher → more flagged).
- *n_neighbors*: neighborhood size (smaller → more local sensitivity; larger → more global / smoother scores).

**How to interpret**
- Outliers/anomalies don’t always mean “bad data” — they can also represent real extremes (storms, cold snaps).
- Use the plots + sample tables to inspect *when* and *how* the flagged points happen.
"""
)

# global selection (comes from 02_Price_Area_Selector)
AREA = st.session_state.get("selected_area", "NO1")
YEAR = int(st.session_state.get("selected_year", 2024))
st.caption(f"Active selection → **Area:** {AREA} • **Year:** {YEAR}")
st.page_link("pages/02_Price_Area_Selector.py", label="Change area/year", icon=":material/settings:")

# data load (cached)
@st.cache_data(ttl=1800, show_spinner=False)
def get_weather(area: str, year: int) -> pd.DataFrame:
    df = load_openmeteo_era5(area, year).copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)

df = get_weather(AREA, YEAR)

# column names used by the loader
COL_TEMP = "temperature_2m (°C)"
COL_PREC = "precipitation (mm)"

tabs = st.tabs(["Outlier / SPC (Temperature)", "Anomaly / LOF (Precipitation)"])


# TAB 1 — SPC-style temperature outliers via DCT low-pass trend + robust bounds
with tabs[0]:
    if COL_TEMP not in df.columns:
        st.warning(f"Column `{COL_TEMP}` not found in the weather dataset.")
        st.stop()

    # controls
    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        keep_frac = st.slider(
            "Keep low-frequency fraction (DCT)",
            min_value=0.001,
            max_value=0.05,
            value=0.01,
            step=0.001,
            help="Fraction of the lowest DCT coefficients kept in the trend "
                 "(e.g., 0.01 ≈ first 1% of coefficients).",
        )
    with c2:
        k_sigma = st.slider(
            "SPC width (k·σ₍robust₎)",
            1.0,
            6.0,
            3.0,
            0.1,
            help="Half-width of control band in units of robust σ (MAD-based).",
        )
    with c3:
        st.caption("SPC-based outlier detection: trend via DCT low-pass; bounds = trend ± k·σ₍robust₎.")

    # Make a time-indexed series (function will regularize to hourly + interpolate)
    ts = df.copy()
    ts["time"] = pd.to_datetime(ts["time"], utc=True)
    ts = ts.set_index("time").sort_index()

    out_df, summ = spc_outliers_dct(
        ts[COL_TEMP],
        keep_frac=float(keep_frac),
        k_sigma=float(k_sigma),
        interp_limit=6,
    )

    if out_df.empty or summ.n_points < 24:
        st.info("Not enough data points to analyze.")
        st.stop()

    # summary
    pct = (100 * summ.n_outliers / summ.n_points) if summ.n_points else 0.0
    st.caption(
        f"Points: **{summ.n_points:,}** • Outliers: **{summ.n_outliers:,}** "
        f"({pct:.2f}%) • σᵣ ≈ {summ.sigma_robust:.3g} • "
        f"max |SATV| ≈ {summ.max_abs_satv:.2f}"
    )

    # plotly figure
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=out_df["time"], y=out_df["lo"], mode="lines",
        line=dict(width=0), name="Lower bound", hoverinfo="skip", showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=out_df["time"], y=out_df["hi"], mode="lines",
        fill="tonexty", fillcolor="rgba(200,200,200,0.2)",
        line=dict(width=0), name="Control band", hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter(
        x=out_df["time"], y=out_df["trend"], mode="lines",
        line=dict(width=1.6, dash="dash"), name="Trend (DCT low-pass)"
    ))
    fig.add_trace(go.Scatter(
        x=out_df["time"], y=out_df["value"], mode="lines",
        line=dict(width=1.2), name=COL_TEMP
    ))

    if summ.n_outliers:
        fig.add_trace(go.Scatter(
            x=out_df.loc[out_df["is_outlier"], "time"],
            y=out_df.loc[out_df["is_outlier"], "value"],
            mode="markers",
            marker=dict(size=6, color="#E15759"),
            name="Outliers",
        ))

    fig.update_layout(
        xaxis_title="Time (UTC)",
        yaxis_title="Temperature (°C)",
        hovermode="x unified",
        margin=dict(t=10, r=10, b=10, l=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Sample outliers (first 30)"):
        st.dataframe(
            out_df.loc[out_df["is_outlier"]].head(30),
            use_container_width=True
        )


# TAB 2 — LOF anomalies for precipitation data
with tabs[1]:
    if COL_PREC not in df.columns:
        st.warning(f"Column `{COL_PREC}` not found in the weather dataset.")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        contamination = st.slider(
            "LOF contamination", 0.001, 0.05, 0.01, 0.001,
            help="Approximate fraction of anomalies."
        )
    with c2:
        n_neighbors = st.slider(
            "LOF n_neighbors",
            min_value=10,
            max_value=120,
            value=60,
            step=5,
            help="Size of the local neighbourhood used by LOF. Larger values give smoother, more global anomaly scores; "
                 "smaller values focus on very local deviations."
        )

    s = pd.to_numeric(df[COL_PREC], errors="coerce").fillna(0.0)
    nonzero = int((s > 0).sum())
    if nonzero < 10:
        st.info("Precipitation is mostly zero — not enough variation for LOF.")
        st.stop()

    a_df, n_eff = lof_precip_anomalies(
        df,
        time_col="time",
        precip_col=COL_PREC,
        contamination=float(contamination),
        n_neighbors=int(n_neighbors),
        roll_hours=24,
    )

    if a_df.empty:
        st.info("Could not compute LOF anomalies for this selection.")
        st.stop()

    n_anom = int(a_df["is_anom"].sum())
    st.caption(
        f"Points: **{len(a_df):,}** • Anomalies: **{n_anom:,}** "
        f"({(100*n_anom/len(a_df)):.2f}%) • n_neighbors={n_eff}"
    )

    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(
        x=a_df["time"], y=a_df["precip"],
        mode="lines", name="Precipitation (mm)", line=dict(width=1.2)
    ))
    if n_anom:
        fig_p.add_trace(go.Scatter(
            x=a_df.loc[a_df["is_anom"], "time"],
            y=a_df.loc[a_df["is_anom"], "precip"],
            mode="markers", name="Anomalies",
            marker=dict(size=6, color="#E15759")
        ))
    fig_p.update_layout(
        xaxis_title="Time (UTC)", yaxis_title="mm",
        hovermode="x unified",
        margin=dict(t=10, r=10, b=10, l=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig_p, use_container_width=True)

    with st.expander("Sample anomalies (first 30)"):
        st.dataframe(
            a_df.loc[a_df["is_anom"]].head(30),
            use_container_width=True
        )