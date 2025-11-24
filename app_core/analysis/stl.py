
#stl.py
import pandas as pd
from statsmodels.tsa.seasonal import STL
import plotly.graph_objects as go

def stl_decompose_elhub(
    df,
    area="NO1",
    group="solar",
    period=24,
    seasonal=13,
    trend=365,
    robust=True,
    time_col="start_time",
    area_col="price_area",
    group_col="production_group",
    value_col="quantity_kwh",
):
    d = df[(df[area_col] == area) & (df[group_col] == group)].copy()
    if d.empty:
        return {}, {"error": f"No data for area={area}, group={group}"}, d

    d[time_col] = pd.to_datetime(d[time_col], utc=True, errors="coerce")
    d = d.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)

    y = d[value_col].astype(float)
    if y.index.inferred_freq is None:
        y = y.resample("h").sum()

    if seasonal % 2 == 0:
        seasonal += 1
    if trend % 2 == 0:
        trend += 1

    res = STL(y, period=period, seasonal=seasonal, trend=trend, robust=robust).fit()

    parts = {
        "observed": y,
        "seasonal": pd.Series(res.seasonal, index=y.index),
        "trend":    pd.Series(res.trend,    index=y.index),
        "resid":    pd.Series(res.resid,    index=y.index),
    }

    figs = {}
    for name, ser, ylabel in [
        ("observed", parts["observed"], "kWh"),
        ("seasonal", parts["seasonal"], "kWh (seasonal)"),
        ("trend",    parts["trend"],    "kWh (trend)"),
        ("resid",    parts["resid"],    "kWh (residual)"),
    ]:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ser.index, y=ser.values, mode="lines", name=name))
        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=30, b=10),
            title=f"{area} — {group}: {name.capitalize()} (STL)",
            xaxis_title="Time (UTC)",
            yaxis_title=ylabel,
            hovermode="x",
        )
        figs[name] = fig

    details = {
        "area": area, "group": group,
        "period": int(period), "seasonal": int(seasonal),
        "trend": int(trend), "robust": bool(robust),
        "n_points": int(len(y)),
    }
    return figs, details, d
