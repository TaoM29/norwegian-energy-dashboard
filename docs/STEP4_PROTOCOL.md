# Step 4 — Forecast feature ablation

Frozen before new variant fits on 2026-09-22. The [versioned JSON protocol](protocols/forecast-ablation-20260922.json)
records the exact columns, dates, settings, input manifest and two comparisons.

## Question and scope

How much predictive value do eligible demand history and weather add to a tuned
linear ridge model? Compare three nested feature sets, with **the same three-alpha
validation budget independently applied per area and variant**:

| Variant | Predictors |
| --- | --- |
| Calendar | 9 columns: horizon, hourly/weekly/annual cyclic encodings, weekend and Norwegian holiday |
| Calendar + demand | Calendar plus 8 demand lags and rolling summaries |
| Calendar + demand + weather | Above plus 12 eligible temperature, precipitation and wind summaries |

Removed groups are absent from both training and prediction matrices. Removing
demand predictors does not remove the observed training labels, eligibility rules,
seasonal reference or MASE denominator. Removing weather also removes all weather
derived features. There are no new interactions, encodings or model families.

Ridge is a bounded, interpretable comparison, selected after Step 2 outcomes were
known. It does **not** ablate Step 2's stronger gradient-boosting model. These 2025
dates were already inspected: this is exploratory evidence, not untouched
confirmation or evidence of causal weather effects. Revised demand and city-proxy
ERA5 with assumed availability cannot reconstruct operational data vintages.

## Fixed design and retained inputs

Reuse the exact [Step 2 protocol](STEP2_PROTOCOL.md) dates: 12 validation dates in
2023, 23 calibration dates in 2024 and 46 evaluation dates in 2025, for all five
areas. Retain 24-hour targets, rolling 120-day fits, six-hour training-origin
stride, energy interval end + 48 hours and weather interval end + 120 hours.
Select alpha from 0.1, 1 and 10 using the existing validation coverage/MAE rule.
Keep fold-local imputation/scaling and independently freeze each area/variant's
10th/50th/90th signed-residual calibration quantiles before evaluation.

Read only the retained Step 2 CSVs, with round-trip floating-point parsing and
checksum verification. The frozen manifest SHA-256 is
`394f07ddfd02bd5ea4c8d3a6ec40297112b9e1799f24ea64dc22367e78128519`.
Do not refresh upstream sources, overwrite the parent bundle or replace old
results. Retain protocol, execution source archive and each raw variant result
before publishing the combined artifact locally.

All comparisons use **one intersection** of complete successful area-origins
across the three variants and the seasonal reference. Keep each attempt, failure,
pre-intersection support and successful excluded prediction in the audit record.
Do not inherit Step 2's SARIMAX exclusions: SARIMAX is not a participant here.
Consequently, direct numerical comparisons with Step 2 require reconciliation
of cohorts; their shared schedule alone does not make headline scores comparable.

## Predeclared comparisons and uncertainty

The two sequential contrasts are **calendar + demand minus calendar**, and
**calendar + demand + weather minus calendar + demand**. Report absolute MAE,
RMSE, bias (`actual − prediction`), coverage, width and all three quantile losses,
plus area support. For error and quantile losses, a negative contrast favors the
added group. Coverage differences are percentage points, with nominal 80% shown;
neither sign universally indicates improvement. Narrower width alone is not better.

Use the Step 2 noncircular moving-block policy: 2,000 resamples, seed 20260921 and
blocks of 2, 4 and 8 scheduled issue dates. Every variant, area and horizon shares
the date draws. Keep empty scheduled dates and weight retained hourly rows equally.
Aggregate squared errors before taking the RMSE root, then subtract variants
**within each replicate**; never subtract marginal confidence-interval endpoints.
Show all three approximate 95% intervals. Withhold intervals for irregular
cadence, fewer than three observed blocks' worth of dates or fewer than 95%
nonempty resamples. These thresholds do not establish validity.

Only one annual cycle is observed. Dependence, nonstationarity, endpoint
under-sampling by noncircular blocks, selective failures and model selection limit
inference. These intervals condition on the selected models and frozen interval
calibration; they do not include their estimation uncertainty. Finding
no added weather value within this ridge specification is a valid outcome; the
evaluation must not trigger a new tuning search.

## Execution and replay

```sh
.venv/bin/python scripts/run_forecast_ablation.py

# Replay into new identities; original evidence is never overwritten.
.venv/bin/python scripts/run_forecast_ablation.py \
  --result-id step4-household-ablation-20260922-replay
```

The runner verifies the frozen feature schema and parent settings before fitting.
Raw variant runs and the source archive live in an ignored `data/analyses/*-runs`
directory. The combined result uses the existing immutable forecast store and
read-only API, including the complete artifact download. Fitting happens offline,
never on page visits. Public publication requires the existing [snapshot release
workflow](RELEASE.md); this step alone neither uploads data nor deploys the site.
