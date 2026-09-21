# Step 2 — Forecast reliability protocol

Frozen on 2026-09-21 before the new evaluation run. The exact settings and dates
are in [the versioned JSON protocol](protocols/forecast-reliability-20260921.json).
Results will be recorded separately in [Step 2 validation](STEP2_VALIDATION.md).

## Question and evidence status

Do the existing models improve on weekly seasonal repetition across more dates,
and do their nominal 80% intervals have useful coverage and width?

This is an **exploratory retrospective study**, not a new untouched holdout.
Step 1 already examined 2025 demand and temperature, and earlier development
informed the model families. Later-revised Elhub observations and ERA5 reanalysis
with assumed publication lags cannot reconstruct historical operational forecasts.
Confirmation requires genuinely uninspected observations and a separately frozen
protocol. No such confirmation claim is made here.

## Frozen design

| Setting | Decision |
| --- | --- |
| Task | Hourly household energy, kWh, NO1–NO5; 24-hour target windows |
| Validation | 15th of each month in 2023: 12 dates per area |
| Calibration | 2024-01-01 through 2024-12-18, every 16 days: 23 dates per area |
| Final exploratory evaluation | 2025-01-01 through 2025-12-27, every 8 days: 46 dates per area |
| Issue time | 00:00 UTC; target intervals `[issue, issue + 24 h)` |
| Training | Rolling 120 days; historical training origins every six hours |
| Availability | Energy interval end + 48 hours; weather interval end + 120 hours |
| Models | Existing seasonal naive, ridge, gradient boosting and ARMA(1,1) benchmark |
| Selection | Existing candidates, per-area chronological validation; full settings in JSON |
| Intervals | Existing per-area/model empirical signed-residual 10th/50th/90th quantiles |
| Weather | Eligible historical city proxies only; no realized target weather |

Eight-day spacing rotates through weekdays and covers all months and seasons.
The calibration sample spans a full year and is substantially larger than the
original three dates. Selection and calibration stop before evaluation; gaps
exceed the required 72-hour horizon-plus-energy-lag embargo. Earlier evaluation
observations can enter later rolling fits only after they become eligible.
Neither hyperparameters nor calibration quantiles are updated using evaluation
errors. No alternate interval method is selected in this study.

The development-only NO1 pilot used 2023-06-01 for validation, 2023-09-01 for
calibration and 2023-12-01 for evaluation. All four existing models ran in
20.258 seconds. Its scores were not used to select the study cadence. The full
run is expected to take tens of minutes and is executed explicitly offline.
The engine permits at most 96 origins per stage; interactive jobs retain their
24-origin limit, existing timeout and bounded queue.

## Input retention and eligibility

Before fitting, the runner retains per-area regular UTC CSVs containing household
demand and the three weather variables, source provenance, exact protocol,
coverage audit and a SHA-256 manifest. Initial fits and replays both read those
serialized inputs with round-trip float precision. No upstream refresh occurs.
Flagged energy observations remain missing; values are never interpolated or
replaced with zero. Duplicate timestamps and incompatible energy units are rejected.

The input audit reports target support, eligible training hours and unavailable
feature cells for every planned origin. The unchanged evaluator requires complete
finite targets and usable baseline references, fits imputation/scaling inside each
training fold, and records fit/convergence failures. Headline comparisons use only
area-origins where **every requested model succeeds**. Successful predictions
outside that cohort do not enter headline scores. All attempts, successes,
exclusions and reasons remain visible; a failed model can select this cohort.

Missing feature cells can be imputed only from that fold's training inputs.
Coverage checks do not certify historical publication vintages or spatial
representativeness of the city proxies.

## Metrics, dependence and uncertainty

Recompute scores from saved prediction rows. Retain MAE, RMSE, MASE, paired
baseline differences, interval coverage, mean width and all three quantile
losses, including area/season/horizon/peak breakdowns and their support. Bias is
`actual − prediction`: positive means underprediction. Negative model-minus-baseline
error differences favor the model. MASE below one does not establish baseline
improvement on the evaluation cohort.

The aggregate weights each matched hourly row equally. Raw kWh errors are affected
by regional scale; area-specific metrics remain necessary. Dates shared across
regions are not independent, and hourly rows are not independent experiments.

Use 2,000 noncircular moving-block bootstrap replicates with seed 20260921 and
prespecified block lengths of **2, 4 and 8 scheduled dates**. Keep every region,
horizon and model on each sampled date together, using the same date draws for
paired model/baseline comparisons. Retain empty dates on the original schedule.
Recompute row-weighted losses from sampled sums; take RMSE square roots after
aggregation. Do not resample individual hours or average per-origin RMSEs.

Report approximate 95% percentile intervals and all three block-length results.
These correspond to roughly 16/32/64-day sampling spans; eight-date blocks give
only about six blocks' worth of observations. Intervals are withheld with fewer
than three observed blocks' worth of dates, irregular cadence, or fewer than 95%
nonempty resamples. These are reporting rules, not validity guarantees. Annual
seasonality, nonstationarity, selective fit failures, model selection and multiple
comparisons limit inference. Seasonal breakdowns are descriptive. No significance
badges or guaranteed future coverage claims are justified.

Noncircular blocks avoid creating a December-to-January transition, but they
under-sample observations near the year's endpoints. This can move the bootstrap
distribution away from the full-year estimate, especially with eight-date blocks.
The [arch time-series bootstrap documentation](https://arch.readthedocs.io/en/latest/bootstrap/timeseries-bootstraps.html)
describes this limitation; it is an explicit tradeoff of this frozen exploratory
method, not a general recommendation for noncircular blocks. Chronological rolling
fits follow the [rolling-origin evaluation principle](https://otexts.com/fpp3/tscv.html),
with the additional publication-lag constraints above.

Residual checks use exact elapsed-time matches. Show within-window one-hour
correlation, exact 24/168-hour pairs, and origin-mean residual correlation at
8/16-day separations, with counts and unavailable values when unsupported.
At this sparse cadence the 24/168-hour checks may have zero pairs; compressed
row shifts must not manufacture those correlations.

## Execution and replay

```sh
# Retain and audit inputs before fitting; refuses to overwrite an existing bundle.
.venv/bin/python scripts/run_forecast_reliability.py --prepare-only

# Execute the frozen study; refuses to overwrite an existing result identity.
.venv/bin/python scripts/run_forecast_reliability.py \
  --input-dir data/analyses/step2-household-reliability-20260921-inputs

# Optional full replay, from exactly the same retained inputs and protocol.
# First check the manifest against the hash recorded in the original result.
printf '%s  %s\n' \
  394f07ddfd02bd5ea4c8d3a6ec40297112b9e1799f24ea64dc22367e78128519 \
  data/analyses/step2-household-reliability-20260921-inputs/manifest.json \
  | shasum -a 256 -c &&
.venv/bin/python scripts/run_forecast_reliability.py \
  --input-dir data/analyses/step2-household-reliability-20260921-inputs \
  --result-id step2-household-reliability-20260921-replay
```

Results use the existing immutable forecast store and read-only API. The study
appears as a separate saved result in Forecasts. The original
`phase4-household-24h` artifact and [Phase 4 record](PHASE4_VALIDATION.md) are
preserved. Expensive fitting never happens on page visits. Production publication
uses the existing [snapshot workflow](RELEASE.md); a local result alone does not
update the public site.
