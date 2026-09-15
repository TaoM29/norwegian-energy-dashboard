# Phase 4 — Forecasting and evaluation

The Forecasts workspace separates stored results from explicit custom jobs. The flagship task is hourly household demand in NO1–NO5 with a 24-hour horizon. SARIMAX experiments retain production/consumption groups, hourly/daily aggregation, training dates, model orders, seasonal orders, weather scenarios, dynamic fitted values and rolling-origin baseline comparisons.

## Availability and leakage audit

The issue time is the start of the first forecast interval: a 24-hour forecast targets `[issue, issue + 24 h)`. An energy observation becomes eligible only after its interval ends and the configured publication lag has elapsed; weather follows its own lag. Default benchmark assumptions are 48 hours for energy and 120 hours for ERA5 weather. These are explicit experimental assumptions, not verified historical publication timestamps. Local energy snapshots contain later revisions, and ERA5 is reanalysis. Consequently, this is a retrospective, availability-assumed evaluation rather than a reconstructed operational backtest.

Historical weather features use only observations eligible at each origin. A separate `realized_future_upper_bound` mode can examine the value of perfect future weather and is labeled accordingly. Archived operational weather forecasts are not available in this repository; no experiment presents realized weather as an issued forecast.

The Phase 0 inventory identified global weather interpolation/backfilling, compressed missing-target grids, omitted fit failures, unmatched model folds and incorrect MASE interpretation in the old workflow. The new engine retains the hourly grid and excludes unavailable features/targets explicitly. Preprocessing and parameter selection use chronological training/validation data. Interval calibration precedes the final holdout, with an embargo long enough for the preceding stage’s target observations to be published. Later holdout origins may causally refit on earlier holdout observations once those observations become available; hyperparameter selection and residual calibration remain frozen. Failed fits remain recorded and headline model comparisons use matched successful origins.

The retained Streamlit page remains runnable and now labels its exogenous backtest as a realized-weather upper-bound experiment. Its historical controls and plots are retained until the release phase. It is not the new availability-aware evaluation path.

## Custom SARIMAX behavior

Training targets remain on a regular UTC grid; state-space fitting handles missing training observations. A missing final training value or insufficient history produces an explicit failure. Daily energy totals require 24 observed hours. Weather regressors use past-only filling and either last-value or hour-of-day/day-of-week means constructed from the history available at that origin. The model forecasts through the publication-lag gap before returning the requested horizon.

Forecast intervals are nominal 95% SARIMAX intervals, conditional on fitted parameters and the supplied weather scenario. They omit uncertainty in future weather. Fitted and dynamic in-sample curves are descriptive diagnostics, not held-out forecast evidence. AIC is a fit statistic, not a replacement for baseline comparison. MASE uses a training seasonal-error scale: compare held-out MAE/RMSE directly to the held-out seasonal-naive baseline.

The interactive runner limits training to 366 days, horizons to 168 hourly or 60 daily steps, backtests to five folds, and SARIMAX state dimension to 64. This intentionally narrows the legacy page's expensive order/horizon combinations. Jobs expose status, progress, cancellation and failure; expensive fitting never occurs inside an ordinary result-read request.

## Storage and reproducibility

`data/forecasts/` contains ignored local result and job JSON files, written atomically. There is one active worker and a bounded queue; cancellation terminates its process. Interrupted runs remain failed records after restart. Results include dataset versions, time windows, issue times, feature definitions, parameters, model metrics, code revision, source fingerprint and dependency versions. Exact reruns require the same published source snapshots and dependency versions; a refresh can legitimately change inputs. Stored prediction rows retain actual targets and model outputs so their reported metrics remain independently recomputable. The Python API serves stored artifacts; a CLI can regenerate the benchmark without clicking through the UI.

## Method references

Training-only preprocessing follows the [scikit-learn leakage guidance](https://scikit-learn.org/1.8/common_pitfalls.html). Forecast and conditional interval extraction uses [statsmodels SARIMAX results](https://www.statsmodels.org/v0.14.1/generated/statsmodels.tsa.statespace.sarimax.SARIMAXResults.html). Repository fixtures additionally verify missing-hour preservation and publication-time feature boundaries.

## Benchmark protocol

The recorded run uses 120-day training windows and a six-hour stride between historical training origins. Ridge tunes alpha over 0.1, 1 and 10; gradient boosting compares two predeclared depth/learning-rate configurations. The baseline repeats available observations at a 168-hour lag. The benchmark SARIMAX comparison uses a fixed nonseasonal ARMA(1,1) with fold-local scaling and 75 optimizer iterations; seasonal orders remain available in custom experiments. These choices were frozen before inspecting holdout errors.

Calendar features use Europe/Oslo hour, weekday, day of year, weekends and Norwegian holidays; data timestamps stay UTC. Shifted demand levels and 24/168-hour rolling summaries use only eligible observations. Historical weather features cover temperature, precipitation and wind speed. Imputation/scaling fit on each fold’s training data only. Empirical 10th/50th/90th residual quantiles are calibrated before holdout, yielding nominal 80% intervals. Their observed coverage is measured; no distribution-free coverage guarantee is claimed.

The representative holdout has four days per area, one in each season. This is a transparent benchmark sample, not evidence of seasonal superiority or statistical significance. Calibration uses three days per area and pools their hourly residuals. Broader evaluation is supported through configurable origins without changing the engine.

Regenerate the recorded configuration against the same snapshots:

```sh
.venv/bin/python scripts/run_forecast_benchmark.py \
  --validation-origin 2025-02-01T00:00:00Z \
  --validation-origin 2025-05-01T00:00:00Z \
  --validation-origin 2025-08-01T00:00:00Z \
  --calibration-origin 2025-10-01T00:00:00Z \
  --calibration-origin 2025-11-01T00:00:00Z \
  --calibration-origin 2025-11-15T00:00:00Z \
  --holdout-origin 2025-12-01T00:00:00Z \
  --holdout-origin 2026-03-01T00:00:00Z \
  --holdout-origin 2026-06-01T00:00:00Z \
  --holdout-origin 2026-09-01T00:00:00Z
```

## Recorded validation

The all-five-area run `phase4-household-24h` completed on 2026-09-15 in **241.06 seconds**. Its local artifact is `data/forecasts/results/phase4-household-24h.json`. The run captured base commit `b2c46c0dcdcd7ab343470d022f7394d0e71b3646`, an uncommitted working tree and source fingerprint `1cb1442485cf6909d9bd3bf0635bd2d2fb6391d1b99a2875c35c64044af379be`. Python was 3.11.13, scikit-learn 1.9.1 and statsmodels 0.15.0.

There were 20 attempted area-origins and **19 matched area-origins**, yielding 456 hourly targets per model. SARIMAX did not converge for NO2 on 2026-03-01; that origin was excluded from every model's headline cohort. A separate SARIMAX calibration failure occurred for NO3 on 2025-11-01. Both remain recorded in the artifact. The other four areas retain all four holdout dates; NO2 retains three. Metrics also include area, season, horizon and local peak-period breakdowns.

| Model | MAE (kWh) | RMSE (kWh) | MASE | Observed 80% interval coverage | Mean width (kWh) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Seasonal naive | 88,508.58 | 159,440.58 | 0.812 | 46.5% | 377,510.58 |
| Ridge | 90,022.25 | 130,145.87 | 0.920 | 58.1% | 333,459.04 |
| Gradient boosting | 61,991.89 | 94,135.39 | 0.632 | 61.6% | 319,206.60 |
| SARIMAX | 183,060.77 | 253,872.82 | 1.990 | 29.2% | 420,032.63 |

Gradient boosting reduced aggregate MAE by 29.96% relative to the baseline on this small matched sample. Ridge's MAE was 1.71% worse despite MASE below one. All nominal 80% intervals undercovered; these intervals are not established as reliable operational uncertainty estimates. Quantile losses, failures and calibration details are available in the saved result and metadata download. No model was retuned after inspecting these holdout results.

Validation completed with 168 Python tests, TypeScript checking and a production Next.js build. Real custom hourly and daily/weather SARIMAX runs completed; running-job cancellation terminated the worker. API tests cover persistence, failure, timeout and restart handling. Browser checks covered saved benchmark metrics, area/breakdown controls, custom-job completion, forecast and diagnostic charts, URL state, and a 390-pixel mobile layout without horizontal page overflow. CSV, JSON and PNG export controls reuse the shared download paths; metadata includes selected parameters, calibration, cohort coverage and failures.

The gate is met for the implemented retrospective workflow. Operational deployment, archived issue-time weather, broader reliability claims and Streamlit retirement remain outside this phase.
