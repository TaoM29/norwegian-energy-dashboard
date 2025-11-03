
# stl.py
import pandas as pd, matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import STL

def stl_decompose_elhub(df, area="NO1", group="solar", period=24, seasonal=13, trend=365, robust=True,
                        time_col="start_time", area_col="price_area", group_col="production_group", value_col="quantity_kwh"):
    d = df[(df[area_col]==area) & (df[group_col]==group)].copy()
    if d.empty: raise ValueError(f"No data for area={area}, group={group}")
    d[time_col]=pd.to_datetime(d[time_col]); d=d.sort_values(time_col).set_index(time_col)
    y = d[value_col].astype(float)
    if y.index.inferred_freq is None: y = y.resample("h").sum()
    if seasonal%2==0: seasonal+=1
    if trend%2==0: trend+=1
    res = STL(y, period=period, seasonal=seasonal, trend=trend, robust=robust).fit()
    figs={}
    for name, series, ylabel in [
        ("observed", y.values, "kWh"), ("seasonal", res.seasonal, "kWh (seasonal)"),
        ("trend", res.trend, "kWh (trend)"), ("resid", res.resid, "kWh (resid)")
    ]:
        f, ax = plt.subplots(figsize=(11,3))
        ax.plot(y.index, series, lw=1.0, label=name.capitalize() if name!="resid" else "Residual")
        ax.set_title(f"{area} — {group}: {name.capitalize() if name!='resid' else 'Residual'} (STL)")
        ax.set_xlabel("Time"); ax.set_ylabel(ylabel); ax.grid(True, alpha=.25); ax.legend()
        figs[name]=f
    details={"area":area,"group":group,"period":period,"seasonal":seasonal,"trend":trend,"robust":robust,"n_points":int(len(y))}
    return figs, details, d
