
# spectrogram.py
import numpy as np, pandas as pd, matplotlib.pyplot as plt, matplotlib.dates as mdates
from scipy.signal import spectrogram

def plot_production_spectrogram(df, area="NO1", group="solar", window_len=168, overlap=84,
                                time_col="start_time", area_col="price_area", group_col="production_group", value_col="quantity_kwh"):
    d = df[(df[area_col]==area) & (df[group_col]==group)].copy()
    if d.empty: raise ValueError(f"No data for area={area}, group={group}")
    d[time_col]=pd.to_datetime(d[time_col]); d=d.sort_values(time_col).set_index(time_col)
    y = d[value_col].astype(float).resample("h").sum().asfreq("h").interpolate("time", limit=3).fillna(0.0)
    fs=1.0
    f, t, Sxx = spectrogram(y.values, fs=fs, window="hann", nperseg=window_len, noverlap=overlap, detrend="constant", scaling="density", mode="psd")
    t_dt = y.index[0] + pd.to_timedelta(t, unit="h")
    fig, ax = plt.subplots(figsize=(11,4))
    im = ax.pcolormesh(t_dt, f, Sxx, shading="gouraud")
    ax.set_ylabel("Frequency (cycles/hour)"); ax.set_xlabel("Time")
    ax.set_title(f"Spectrogram — {area} / {group}  (nperseg={window_len}, overlap={overlap})")
    ax.set_ylim(0, 0.5); ax.grid(True, alpha=.2)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.colorbar(im, ax=ax).set_label("Power (PSD)")
    fig.tight_layout()
    return fig, f, t_dt, Sxx, y
