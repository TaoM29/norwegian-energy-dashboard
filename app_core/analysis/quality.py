
# qc_utils.py
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from scipy.fft import dct, idct
from sklearn.neighbors import LocalOutlierFactor

def plot_temperature_outliers_dct(df, time_col="time", temp_col="temperature_2m (°C)", cutoff_fraction=0.10, k_sigma=3.0, title=None):
    s = df[[time_col, temp_col]].dropna().sort_values(time_col)
    t = pd.to_datetime(s[time_col].values); x = s[temp_col].astype(float).values; n=len(x)
    K = max(1, int(np.floor(cutoff_fraction*n)))
    Xc = dct(x, type=2, norm="ortho"); Xc_lp = np.zeros_like(Xc); Xc_lp[:K] = Xc[:K]
    baseline = idct(Xc_lp, type=2, norm="ortho"); satv = x - baseline
    med = np.median(satv); mad = np.median(np.abs(satv - med)); robust_sigma = 1.4826*mad
    upper = baseline + (med + k_sigma*robust_sigma); lower = baseline + (med - k_sigma*robust_sigma)
    is_out = (x>upper)|(x<lower)
    fig, ax = plt.subplots(figsize=(11,4.5))
    ax.plot(t, x, lw=1.0, label="Temperature (°C)")
    ax.plot(t, upper, "--", lw=1.0, label=f"SPC upper (k={k_sigma})")
    ax.plot(t, lower, "--", lw=1.0, label=f"SPC lower (k={k_sigma})")
    ax.scatter(t[is_out], x[is_out], s=18, zorder=3, label="Outliers")
    ax.set_xlabel("Time"); ax.set_ylabel("Temperature (°C)"); ax.set_title(title or "Temperature with SPC Outlier Bands (DCT)")
    ax.legend(); ax.grid(True, alpha=.25)
    outliers = s.loc[is_out, [time_col, temp_col]].copy(); outliers["baseline"]=baseline[is_out]; outliers["deviation"]=(x-baseline)[is_out]
    summary = {"n_points": int(n), "n_outliers": int(is_out.sum()), "outlier_pct": float(is_out.mean()*100),
               "cutoff_fraction": float(cutoff_fraction), "k_sigma": float(k_sigma), "robust_sigma": float(robust_sigma), "median_satv": float(med)}
    return fig, summary, outliers

def plot_precip_anomalies_lof(df, time_col="time", precip_col="precipitation (mm)", contamination=0.01, n_neighbors=60, jitter_eps=1e-6, use_log1p=True, title=None):
    s = df[[time_col, precip_col]].dropna().sort_values(time_col)
    t = pd.to_datetime(s[time_col].values); y = s[precip_col].astype(float).values.copy()
    if jitter_eps: 
        z = (y==0.0); 
        if z.any(): 
            rng=np.random.default_rng(0); y[z] = y[z] + rng.uniform(-jitter_eps, jitter_eps, size=z.sum())
    if use_log1p: y = np.log1p(y)
    Y = y.reshape(-1,1); n_neighbors = int(min(max(5, n_neighbors), len(Y)-1))
    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination, novelty=False)
    y_pred = lof.fit_predict(Y); scores = -lof.negative_outlier_factor_; is_anom = (y_pred==-1)
    fig, ax = plt.subplots(figsize=(11,4))
    ax.plot(t, s[precip_col].values, lw=1.0, label="Precipitation (mm)")
    ax.scatter(t[is_anom], s[precip_col].values[is_anom], s=20, zorder=3, label="LOF anomalies")
    ax.set_xlabel("Time"); ax.set_ylabel("Precipitation (mm)"); ax.set_title(title or f"Precipitation Anomalies (LOF, contamination={contamination:.2%})")
    ax.legend(); ax.grid(True, alpha=.25)
    anomalies = s.loc[is_anom, [time_col, precip_col]].copy(); anomalies["lof_score"]=scores[is_anom]
    summary = {"n_points": int(len(s)), "n_anomalies": int(is_anom.sum()), "anomaly_pct": float(is_anom.mean()*100),
               "contamination": float(contamination), "n_neighbors": int(n_neighbors)}
    return fig, summary, anomalies
