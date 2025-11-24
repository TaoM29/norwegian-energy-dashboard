
# spectrogram.py
import numpy as np
import pandas as pd
from scipy.signal import spectrogram
import plotly.graph_objects as go

def production_spectrogram(
    df,
    area="NO1",
    group="solar",
    window_len=168,
    overlap=84,
    time_col="start_time",
    area_col="price_area",
    group_col="production_group",
    value_col="quantity_kwh",
    freq_units="cpd",  # "cpd" (cycles/day) or "cph" (cycles/hour)
):
    d = df[(df[area_col] == area) & (df[group_col] == group)].copy()
    if d.empty:
        return None, None, None, None

    d[time_col] = pd.to_datetime(d[time_col], utc=True, errors="coerce")
    d = d.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)

    y = (
        d[value_col].astype(float)
        .resample("h").sum()
        .asfreq("h")
        .interpolate("time", limit=3)
        .fillna(0.0)
    )

    fs = 1.0  # 1 sample per hour
    f, t, Sxx = spectrogram(
        y.values,
        fs=fs,
        window="hann",
        nperseg=window_len,
        noverlap=overlap,
        detrend="linear",
        scaling="density",
        mode="magnitude",
    )
    t_idx = y.index[0] + pd.to_timedelta(t, unit="h")

    if freq_units == "cpd":
        fy = f * 24.0
        ylab = "Frequency (cycles/day)"
    else:
        fy = f
        ylab = "Frequency (cycles/hour)"

    fig = go.Figure(
        data=go.Heatmap(
            x=t_idx,
            y=fy,
            z=Sxx,
            colorscale="Viridis",
            colorbar=dict(title="|X|"),
        )
    )
    fig.update_layout(
        title=f"Spectrogram — {area} / {group} (nperseg={window_len}, overlap={overlap})",
        xaxis_title="Time (UTC)",
        yaxis_title=ylab,
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    if freq_units == "cpd":
        fig.update_yaxes(range=[0, 12])  # show up to 12 cycles/day by default

    return fig, f, t_idx, Sxx
