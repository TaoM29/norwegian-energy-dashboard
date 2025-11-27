
# pages/41_SPC_and_LOF_Data_Quality.py
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scipy.fftpack import dct, idct
from sklearn.neighbors import LocalOutlierFactor

from app_core.loaders.weather import load_openmeteo_era5

st.set_page_config(page_title="Data Quality — SPC & LOF", layout="wide")
st.title("Data Quality — SPC (Outliers) & LOF (Anomalies)")

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

    # Make a time-indexed, hourly series before interpolation
    ts = df.copy()
    ts["time"] = pd.to_datetime(ts["time"], utc=True)
    ts = ts.set_index("time").sort_index()

    # Regular hourly grid → time-weighted interpolation now valid
    s = pd.to_numeric(ts[COL_TEMP], errors="coerce").asfreq("H")
    s = s.interpolate(method="time", limit=6)

    n = int(s.notna().sum())
    if n < 24:
        st.info("Not enough data points to analyze.")
        st.stop()

    # DCT low-pass trend
    y = s.fillna(method="ffill").fillna(method="bfill").to_numpy()
    coeff = dct(y, norm="ortho")
    k = max(1, int(len(y) * keep_frac))
    coeff_lp = np.zeros_like(coeff)
    coeff_lp[:k] = coeff[:k]
    trend = idct(coeff_lp, norm="ortho")

    # robust σ using MAD
    resid = y - trend
    mad = np.median(np.abs(resid - np.median(resid)))
    sigma_robust = 1.4826 * mad if mad > 0 else (np.std(resid) or 1.0)

    band_hi = trend + k_sigma * sigma_robust
    band_lo = trend - k_sigma * sigma_robust
    is_out = (y > band_hi) | (y < band_lo)

    # SATV (standardized actual-to-trend value)
    if sigma_robust:
        satv = resid / sigma_robust
        max_abs_satv = float(np.max(np.abs(satv)))
    else:
        satv = np.zeros_like(resid)
        max_abs_satv = 0.0

    out_df = pd.DataFrame({
        "time": s.index.to_pydatetime(),
        "value": y,
        "trend": trend,
        "lo": band_lo,
        "hi": band_hi,
        "satv": satv,
        "is_outlier": is_out,
    })

    # summary
    n_out = int(is_out.sum())
    st.caption(
        f"Points: **{len(out_df):,}** • Outliers: **{n_out:,}** "
        f"({(100*n_out/len(out_df)):.2f}%) • σᵣ ≈ {sigma_robust:.3g} • "
        f"max |SATV| ≈ {max_abs_satv:.2f}"
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
    if n_out:
        fig.add_trace(go.Scatter(
            x=out_df.loc[out_df["is_outlier"], "time"],
            y=out_df.loc[out_df["is_outlier"], "value"],
            mode="markers", marker=dict(size=6, color="#E15759"),
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


# TAB 2 — LOF anomalies for precipitation (Plotly)
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
        n_neighbors = st.slider("LOF n_neighbors", 
                                min_value=10,
                                max_value=120,
                                value=60,
                                step=5,
                                help="Size of the local neighbourhood used by LOF. Larger values give smoother, more global anomaly scores; "
                                "smaller values focus on very local deviations."
    )

    s = pd.to_numeric(df[COL_PREC], errors="coerce").fillna(0.0)
    nonzero = (s > 0).sum()
    if nonzero < 10:
        st.info("Precipitation is mostly zero — not enough variation for LOF.")
        st.stop()

    # simple 2D context: current value + 24h rolling mean
    roll = s.rolling(24, min_periods=1).mean()
    X = np.column_stack([s.values, roll.values])

    # clamp neighbors to dataset size
    n_eff = min(int(n_neighbors), max(10, len(s) - 1))
    lof = LocalOutlierFactor(n_neighbors=n_eff, contamination=float(contamination))
    labels = lof.fit_predict(X)        # -1 = outlier
    scores = -lof.negative_outlier_factor_

    a_df = pd.DataFrame({
        "time": df["time"],
        "precip": s,
        "roll24": roll,
        "lof_score": scores,
        "is_anom": labels == -1,
    })

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