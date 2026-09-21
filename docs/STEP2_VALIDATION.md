# Step 2 — Broader forecast reliability

Completed locally on 2026-09-22 (Europe/Oslo), following protocol freeze and
execution on 2026-09-21 UTC. No commit, push, snapshot upload or deployment was
performed for this step.
The [frozen protocol](STEP2_PROTOCOL.md) and
[exact JSON settings](protocols/forecast-reliability-20260921.json) predate score
inspection. This record does not replace the [original Phase 4 evidence](PHASE4_VALIDATION.md).

## Retained inputs and execution

The development-only runtime pilot took 20.258 seconds for NO1 with one date per
stage and the four existing models. The broader study uses 12 validation dates
in 2023, 23 calibration dates in 2024, and 46 evaluation dates in 2025, in all five
areas. The period is explicitly exploratory because Step 1 already inspected
2025 observations.

The bundle is `data/analyses/step2-household-reliability-20260921-inputs/`.
Its manifest SHA-256 is
`394f07ddfd02bd5ea4c8d3a6ec40297112b9e1799f24ea64dc22367e78128519`.
Each CSV retains 28,969 consecutive hourly positions from 2022-09-08 00:00 UTC
through 2025-12-28 00:00 UTC inclusive. All five areas have complete household
energy and the three weather variables over that grid. All 405 planned
area-origins have complete targets and eligible training history, with no missing
issue-time feature cells. This is source coverage, not successful-fit coverage.

| Area | Retained CSV SHA-256 |
| --- | --- |
| NO1 | `648e636e10f4aa9e43a6379631b5441dd060ab4730736aa2a295dbdfdaf26558` |
| NO2 | `4b1695aff3eb2dc8c338963f6987fddc6aab00969297ba66f401239dacb4c177` |
| NO3 | `617f8192a3c6a4890333daf7322943fb40edd32e832ec62510df7c32a54eef66` |
| NO4 | `fafad8643e4c050f1e930f4eabd0dd5e5b5233eb2764ea90cf00b8116c8825db` |
| NO5 | `becfbe4894c19aeee5b744b762bd5183d2fd238a021afee03140524570376054` |

The exact analytical execution sources are retained in the same bundle as
`execution-sources.tar.gz`, SHA-256
`1a202aba5a23d67e989db3cbcdafc37123f714646303a792657dc6c116b72e9c`.
The archive's app-core/backend source fingerprint is
`7583cf0b8ba8135e95f9ca27242e27e8ad3c538924e55bc2468a2066ea180614`;
runner SHA-256 is
`4cf89db8ceb0950e5fc0756b8b53cf30e071239503415827a624d55d4dcd4e94`.
Presentation and streaming delivery were refined while fitting continued; they
do not change the archived analytical code or protocol.

The preserved original `phase4-household-24h.json` SHA-256 is
`ae5a0fc4c144dfb208a2299ecd7f06adec46ce7d6b659f03cb8b0859b710c75e`.

## Implementation

- The existing evaluation engine and candidate models are reused. Offline studies
  allow up to 96 origins per stage; interactive jobs retain 24 and their existing
  queue/timeout limits.
- Saved metrics add signed bias, distinct dates and area-origin counts. Calibration
  records retain residual rows and successful dates for independent quantile checks.
- A pure report calculation reads saved matched predictions, validates paired
  targets and full horizons, and calculates baseline differences and approximate
  date-block uncertainty for MAE/RMSE differences, coverage, width and quantile loss.
  All regions and models share date draws; missing dates remain on the schedule.
- Exact-lag residual diagnostics distinguish unsupported 24/168-hour comparisons
  from within-window and origin-mean correlations, including per-area counts.
- Forecasts shows a separate exploratory reliability summary with fixed-cohort
  support, block-length sensitivity, interval quality, accessible tables and
  per-area residual diagnostics. Existing results remain readable.
- Saved result reads and the complete-study JSON download stream immutable file
  bytes, preserving the larger artifact without a buffered-response size limit.
  Ordinary page visits never fit models.

## Independent checks

The development evidence utility
`data/analyses/forecast-reliability-development/verify_step2.py` independently
recomputes metric rows and calibration quantiles, checks cohort accounting,
verifies retained-input hashes, and checks the original artifact hash. It uses
direct arithmetic rather than the production metric helpers.

```sh
.venv/bin/python data/analyses/forecast-reliability-development/verify_step2.py \
  data/forecasts/results/step2-household-reliability-20260921.json
```

The independent audit passed **25,808 checks** across 144 metric rows,
21,504 saved prediction rows and 11,016 calibration residual rows. It reconciled
all reported metric scopes, calibration quantiles, matched-cohort accounting and
input checksums, with no mismatches. The result's execution fingerprint and runner
hash match the archived sources above. Rebuilding the complete reliability report
from saved predictions and the recorded seed produced an identical report; all
its headline values also reconcile with the independently checked metric rows.
A second complete model-fitting run was not performed.

The verifier, its JSON report, retained inputs, archived execution sources and
raw experimental artifact remain local evidence under ignored data directories.
The tracked protocol, runner, tests and this record describe how to reproduce and
validate the study. A fresh checkout requires the retained inputs or their source
snapshots; checksums alone do not supply them.

## Empirical findings

The immutable result is
`data/forecasts/results/step2-household-reliability-20260921.json`.
It contains 16,313,508 bytes and has SHA-256
`da08ba26d4d1c98ee98c0deb695d174b2365105f50eb9e31e4cf3c19c25c9b95`.
The recorded run duration was 2,059.785 seconds (34.3 minutes). Its UTC generation
time is `2026-09-21T22:01:34.146519Z`.

### Fit support and exclusions

All validation fits succeeded. Calibration succeeded on 23 dates per area/model,
except SARIMAX in NO2: its 2024-03-05 fit did not converge, leaving 22 dates and
528 calibration residuals instead of 552. This failure is retained in the artifact.

Evaluation attempted 230 area-origins per model. Seasonal naive, ridge and gradient
boosting succeeded on all 230; SARIMAX succeeded on 224. The six nonconvergent
SARIMAX fits were excluded from every model's comparison. All 46 scheduled dates
remain represented in at least one area. The matched sample contains 5,376 hourly
observations per model; these are dependent observations, not independent trials.

| Area | Attempted origins | Matched origins | Matched hours per model | Excluded evaluation dates (00:00 UTC) |
| --- | ---: | ---: | ---: | --- |
| NO1 | 46 | 45 | 1,080 | 2025-06-02 |
| NO2 | 46 | 45 | 1,080 | 2025-06-18 |
| NO3 | 46 | 44 | 1,056 | 2025-04-15; 2025-11-01 |
| NO4 | 46 | 46 | 1,104 | None |
| NO5 | 46 | 44 | 1,056 | 2025-03-22; 2025-10-16 |

### Matched overall results

All errors, bias and widths below are in kWh per hourly area observation, pooled
with equal row weights. Bias is actual minus prediction. Larger-demand areas can
contribute larger absolute errors; this is not an equal-weight average of regional
percentage improvements. Nominal predictive interval coverage is 80%.

| Model | MAE | RMSE | MAE minus baseline | Bias | Measured coverage | Mean interval width |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Seasonal naive | 99,905.7 | 158,328.6 | 0.0 | -474.1 | 79.1% | 321,493.8 |
| Ridge | 101,504.3 | 156,028.5 | +1,598.5 | +3,354.6 | 80.3% | 349,816.2 |
| Gradient boosting | 83,674.3 | 131,432.1 | -16,231.5 | -2,945.5 | 77.9% | 276,017.0 |
| SARIMAX | 195,347.0 | 273,169.5 | +95,441.2 | +16,087.0 | 78.5% | 588,961.7 |

Gradient boosting has 16.2% lower pooled MAE and 17.0% lower pooled RMSE than the
seasonal baseline on this matched sample. Its area-level MAE differences are
negative in all five areas, but measured coverage ranges from 71.7% in NO3 to
83.4% in NO4. Ridge's small pooled MAE difference is inconclusive under the
specified uncertainty analysis. The fixed SARIMAX configuration performs worse
than the baseline despite substantially wider intervals. No candidate, date,
calibration setting or failure rule was changed after these results were seen.
The new coverage figures do not establish an improvement over the historical
Phase 4 experiment: the dates and calibration sample differ.

| Model | Lower quantile loss (0.1) | Median quantile loss (0.5) | Upper quantile loss (0.9) |
| --- | ---: | ---: | ---: |
| Seasonal naive | 27,282.6 | 51,320.9 | 26,341.6 |
| Ridge | 23,239.7 | 50,996.8 | 25,495.2 |
| Gradient boosting | 19,358.4 | 42,042.5 | 22,515.8 |
| SARIMAX | 34,251.7 | 97,872.8 | 43,291.7 |

Quantile losses use the separately calibrated quantile predictions, including the
residual-adjusted median; point MAE uses the original model point forecast.

### Dependence and approximate uncertainty

The following are approximate 95% percentile ranges for MAE minus baseline,
using 2,000 shared-date moving-block resamples at each prespecified block length.
Negative differences favor the model. Every resample retained observations.

| Model | 2 dates/block | 4 dates/block | 8 dates/block |
| --- | --- | --- | --- |
| Gradient boosting | -27,636.8 to -4,718.7 | -28,237.9 to -3,026.4 | -26,548.1 to -1,085.6 |
| Ridge | -11,918.0 to +13,624.9 | -11,806.8 to +13,489.0 | -10,479.5 to +7,281.0 |
| SARIMAX | +63,398.6 to +126,185.8 | +55,306.4 to +134,626.2 | +51,892.1 to +138,916.4 |

Gradient boosting's ranges remain below zero for these choices, while ridge's
cross zero. This is conditional exploratory evidence, not a confirmatory test or
a guarantee of future improvement. Only 46 distinct dates and one annual cycle
are available; the 8-date blocks represent about 5.75 observed blocks. Seasonal
nonstationarity, endpoint under-sampling in noncircular blocks, previously reviewed
data, fit exclusions and multiple comparisons limit inference. Complete ranges
for RMSE differences, coverage, interval width and quantile loss are saved in the
artifact. For example, gradient boosting's coverage ranges are 71.5–85.1%,
70.8–87.1% and 70.2–89.3% for the three block lengths, so the observed 77.9% should
not be interpreted as a precise long-run coverage estimate.

Adjacent-hour residual correlations are high (pooled 0.968–0.992, 5,152 pairs
per model). Exact 24-hour and 168-hour comparisons have **zero pairs** because of
the sampled origin cadence; their correlations are unavailable, not zero.
Origin-mean diagnostics use 213 exact 8-day pairs and 208 exact 16-day pairs, with
per-area counts and correlations retained. These pooled diagnostics are descriptive
and can mix regional levels; the UI provides area-specific inspection.


## Software checks

- `.venv/bin/python -m pytest -q`: **265 passed**; two existing dependency
  deprecation warnings. Checks include chronological availability and frozen
  calibration, exact elapsed-time residual pairing, corrupt/partial cohort
  rejection, shared-date regional resampling, sparse support, retained-input
  tamper detection, immutable identities and a five-megabyte streamed artifact.
- Frontend type checking and the production Next.js build passed.
- All five focused Forecasts browser tests passed, including compatibility with
  older artifacts, explicit exploratory wording, fixed-cohort support and
  per-area residual selection.
- The original Phase 4 artifact was also opened in the browser. Its result and
  download endpoints both returned the exact original bytes through the Next.js
  proxy, with the checksum above.
- Documentation links and `git diff --check` passed. No dependency was added.

The completed study was reviewed at 1440×1000 and 390×844 in light and dark
themes. Keyboard activation expands/collapses the support details; selecting NO5
shows its own residual counts and correlations. The phone layout has a 390-pixel
page width with wide tables scrolling inside their own regions. Both the result
and full-download routes returned HTTP 200 through the Next.js proxy and exactly
matched the 16,313,508-byte artifact checksum above.

## Publication state

Step 2 is complete locally and uncommitted. Open Forecasts and select
**Forecast reliability · 46 dates in 2025**. The production site still uses its
previous published snapshot. Publishing this step requires both the code and a
new data snapshot containing the result and updated forecast manifest; a code push
alone does not publish ignored data artifacts. Follow [release operations](RELEASE.md).
Retained input CSVs and the execution-source archive must remain available for
reproducibility even if the serving snapshot contains only the result.
