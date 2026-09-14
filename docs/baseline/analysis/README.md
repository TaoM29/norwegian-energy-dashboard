# Numerical analysis baseline

These files are comparison fixtures for the original Streamlit analysis code. Recreate them from the repository root with:

```bash
.venv/bin/python scripts/capture_analysis_baseline.py
```

`summary.json` records input and source SHA-256 hashes, selections, parameters, compact results, and repeat-agreement checks. The CSV and NPZ files retain the full numerical outputs used for comparison. `timings.csv` is intentionally separate because elapsed times vary between runs; `environment.json` explains the process, cache, platform, and thread conditions.

Energy calculations use tracked NO1 solar production. STL and the spectrogram use January 2021 hourly values. Forecast comparison uses daily totals from January through June 2021, three matched seven-day folds, seasonal naive lag 7, and a real statsmodels SARIMAX `(1,0,0)(1,0,0,7)` fit without exogenous inputs.

Weather calculations use the tracked `open-meteo-subset.csv` exactly over its actual timestamp strings, 2020-01-01 00:00 through 2020-12-30 23:00. Those naive strings are parsed with `utc=True`, matching the existing page, without shifting their clock values. The file does not establish location, model, or authoritative unit provenance, so these fixtures do not add those labels. Snow Drift outputs call function definitions extracted unchanged from the existing page; both July–June seasons in this weather subset are partial.

These are numerical regression references, not evidence of data correctness, verified weather events, operational forecasting skill, or live/browser/network latency. The LOF helper warns that duplicate feature values can affect its result; that warning is retained in `summary.json`.
