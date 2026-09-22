# Step 4 — Forecast feature ablation validation

Completed locally on 2026-09-22 under the [frozen protocol](STEP4_PROTOCOL.md).
Result: `step4-household-ablation-20260922`, titled **Feature ablation · calendar,
demand and weather** in the Forecasts saved-result selector.

## Delivered behavior

The evaluator supports three nested tabular feature sets with 9, 17 and 29
columns. Removed groups, including all derived columns, are absent from both
training and prediction matrices. The default remains the original full feature
set; nondefault sets reject SARIMAX because its feature specification differs.
Weather-free runs do not load weather snapshots. Baseline availability, training
labels and MASE definitions remain intact.

The offline runner checks the frozen configuration and retained Step 2 manifest,
saves source bytes before fitting, and retains each variant result. Its combined
artifact uses one complete matched cohort, records original success/failure
support, and retains successful rows excluded by intersection. Selection and
calibration are saved independently for every area/variant. Earlier frozen
protocols remain replayable without rewriting their original JSON bytes.

Forecasts shows a compact comparison table with proportional MAE bars, signed
incremental differences, all three date-block uncertainty ranges, and expandable
area results, bias, quantile losses, exact features and full paired uncertainty.
The comparison uses the entire saved study independently of chart filters. The
existing forecast chart and error explorer accept all three named ridge variants.
The complete JSON download retains predictions and audit information.

## Execution and support

The run took **1,208.032 seconds (20.1 minutes)**. Every variant retained all
**230 of 230 area-origins**, covering **46 scheduled dates**, five areas and 24
hours per origin. There were **zero recorded validation, calibration or evaluation
failures**, no missing scheduled dates and no intersection exclusions.

Each compared model has **5,520 hourly evaluation rows**; the combined artifact
contains **22,080 rows**, including the seasonal reference once. Calibration has
552 residuals per area/model from the 23 frozen 2024 dates. Calendar selected
alpha 0.1 in every area; calendar + demand selected 10 everywhere; the full set
selected 0.1 in NO1 and 10 in NO2–NO5. These were the predeclared validation choices,
not choices based on evaluation outcomes.

Step 2 had 224 matched area-origins because SARIMAX failed on six. This ablation
does not include SARIMAX and therefore has a different comparison cohort. On the
**5,376 shared hourly ridge targets**, actuals, point forecasts and all three
interval bounds match the earlier Step 2 artifact **exactly**, with maximum
absolute difference zero. Compare the new headline scores on their own cohort.

## Findings

All energy/error values below are kWh; coverage is measured against nominal 80%.
Pooled errors weight hourly rows equally and are affected by regional magnitude.

| Ridge inputs | MAE | RMSE | Bias, actual − forecast | Coverage | Mean width |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calendar | 103,686.9 | 157,141.8 | +755.5 | 77.9% | 336,274.2 |
| Calendar + demand | 96,257.4 | 147,231.7 | +2,383.2 | 78.3% | 307,913.6 |
| Calendar + demand + weather | 100,275.5 | 154,378.1 | +2,622.0 | 80.5% | 349,215.6 |

Adding demand history reduced MAE by **7,429.5 kWh (7.2%)**. Adding eligible
weather to that model increased MAE by **4,018.0 kWh (4.2%)**. Every area's point
MAE followed the same directions. On this shared cohort, the seasonal reference
MAE is 99,443.5 kWh; calendar + demand is 3.2% lower.

Weather increased coverage by 2.2 percentage points, but widened intervals by
41,302.0 kWh (13.4%) and worsened all three quantile losses. Closer-to-nominal
coverage alone is therefore not evidence of better overall interval quality.

| Ridge inputs | Lower pinball | Median pinball | Upper pinball |
| --- | ---: | ---: | ---: |
| Calendar | 24,401.8 | 52,112.3 | 25,646.0 |
| Calendar + demand | 21,727.7 | 48,310.7 | 24,361.5 |
| Calendar + demand + weather | 23,085.9 | 50,395.9 | 25,361.0 |

The approximate 95% paired ranges below are for **added-input minus preceding
variant MAE**, calculated within each of 2,000 common date-block draws:

| Date-block length | Add demand history | Add eligible weather |
| --- | ---: | ---: |
| 2 dates | −16,257.6 to −1,488.2 | +1,437.4 to +6,544.7 |
| 4 dates | −14,436.9 to −2,138.0 | +898.6 to +6,774.6 |
| 8 dates | −13,163.6 to −2,465.5 | +778.5 to +6,408.9 |

All three block choices retain the same direction. This remains an exploratory
result conditional on this ridge specification, selected parameters, calibration
and already inspected year. It does not establish weather's value in other model
families, operational forecasts or causal explanations. One annual cycle,
nonstationarity, dependence and noncircular endpoint weighting limit the ranges.
No evaluation-driven retuning or replacement of earlier studies was performed.

## Verification

- Full Python suite: **289 passed**, with two existing dependency deprecation
  warnings. Tests cover removed-group invariance, exact feature identities,
  eligibility, full horizons, target/reference agreement, cohort intersections,
  missing dates, unequal area support, frozen-input integrity and immutable output.
- Independent row-based audit reconciled **144 metric rows**, **20 calibration
  distributions**, both point contrasts and **42 paired uncertainty ranges**
  (two contrasts × three block lengths × seven measures). It used direct NumPy
  loss calculations and independently generated date draws, without report helpers.
- A deterministic fixture independently gathers sampled rows, including a missing
  date and unequal regional support, to check paired MAE and nonlinear RMSE ranges.
- All **10 focused Forecasts browser tests passed**. After the final MAE-bar
  refinement, the two ablation tests passed again. TypeScript and the production
  build passed. Actual results were visually inspected at 1440px desktop and
  390px mobile widths, in light/dark themes, with keyboard table scrolling,
  expanded details and no page-level horizontal overflow.
- Both the frontend-proxied detail and artifact-download endpoints returned
  HTTP 200 and exactly the saved result bytes; the download has an attachment
  filename. The 20 MB study uses the existing streamed artifact response.
- `git diff --check` passed. The original Phase 4 and Step 2 result hashes are
  unchanged. The frozen source archive matches all 41 included source/config files.

## Retained evidence and publication

The ignored local directory
`data/analyses/step4-household-ablation-20260922-runs/` retains the protocol,
execution metadata, exact source archive, three raw variant artifacts and the
independent verification record. Inputs remain in the original checksummed Step 2
bundle; no upstream refresh was performed.

| Evidence | SHA-256 |
| --- | --- |
| Combined Step 4 result | `900daa45c60a1bc9067517c05e83e698d88c232abcb3cb0a8e615850e470ffc6` |
| Execution source archive | `786ab0880278198383ae060ae9adcd25cdd5fc475b66a9ba9f92629ecd830d5a` |
| Retained Step 2 input manifest | `394f07ddfd02bd5ea4c8d3a6ec40297112b9e1799f24ea64dc22367e78128519` |
| Original Phase 4 result | `ae5a0fc4c144dfb208a2299ecd7f06adec46ce7d6b659f03cb8b0859b710c75e` |
| Original Step 2 result | `da08ba26d4d1c98ee98c0deb695d174b2365105f50eb9e31e4cf3c19c25c9b95` |

No dependency was added. No commit, push, upload, deployment or public data-archive
repinning was performed. Follow [release operations](RELEASE.md) to publish this
saved study later; a code commit alone will not make the locally fitted result
available on the public site.
