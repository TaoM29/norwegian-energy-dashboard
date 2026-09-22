# Step 5 — Contextual demand anomalies

Completed locally on 2026-09-22 under the [frozen protocol](STEP5_PROTOCOL.md).
The saved study is `step5-contextual-demand-anomalies-20260922`.

## Delivered behavior

**Patterns → Demand anomalies** adds a distinct retrospective household-demand
view for NO1–NO5. It shows observed versus calendar/weather-adjusted expected
demand, the calibrated residual envelope, ranked candidate episodes, comparable
historical days, missingness and unsupported-temperature counts. Selecting an
area or candidate persists in the URL and browser history. Expandable tables
provide hourly observations, model-selection scores, calibration support and
study periods; CSV exports and the complete JSON retain numerical detail.
Existing temperature SPC and precipitation LOF remain available.

The engine reuses Step 1's predictor basis, but fits a new chronology: train
preprocessing in 2021–2022, select on 2023, refit coefficients through 2023,
calibrate in 2024 and inspect 2025. Step 1's final coefficients included 2024,
so reusing those coefficients would contaminate the new calibration period.
No settings were changed after inspecting scores. Same-hour realized city-proxy
temperature makes this a retrospective analysis, not a deployable forecast alarm.

The read-only API serves a bounded candidate window and the first 20 ranked
episodes. Full artifacts retain every calibration/evaluation row and all episodes.
The offline runner verifies retained input hashes, records execution source bytes
before fitting and refuses to replace an existing result. Fixture generation
adds a separate, explicitly synthetic demonstration. Snapshot packaging includes
the prepared study when present; no upload or publication was performed.

## Observed results

The run completed in **17.505 seconds**, including five synthetic validation seeds
and all five observed areas. All 43,800 expected evaluation hours had finite demand
and temperature. Of these, **41 hours** were outside the temperature range observed
during model development and remained unscored: 35 in NO3 and six in NO5.

| Area | Selected model | Scored hours | Flagged hours | Flag rate | Candidate episodes |
| --- | --- | ---: | ---: | ---: | ---: |
| NO1 | 4-knot spline | 8,760 | 90 | 1.03% | 25 |
| NO2 | 4-knot spline | 8,760 | 228 | 2.60% | 35 |
| NO3 | 4-knot spline | 8,725 | 59 | 0.68% | 22 |
| NO4 | Linear temperature | 8,760 | 128 | 1.46% | 30 |
| NO5 | 4-knot spline | 8,754 | 226 | 2.58% | 45 |

These are **unlabeled candidate rates**, not false-alarm rates or evidence of
faults. The empirical calibration envelope does not promise a future 1% rate.
NO1 calibration retained 8,718 supported hours on 365 UTC dates, excluding 66
unsupported-temperature hours. Other areas retained all 8,784 hours on 366 dates.
Calibration support and exceedances are also saved by season and local day type;
no sparse subgroup thresholds are fitted.

## Review of representative observed candidates

The following cases were selected descriptively by highest high score, highest
low score and longest duration across areas. All timestamps below are UTC; all
three have complete supported input coverage and three eligible peer days.

| Case | Episode, end exclusive | Peak actual / expected kWh | Peak temperature | Peak score |
| --- | --- | ---: | ---: | ---: |
| NO2, highest high | Dec 18 20:00–Dec 19 06:00 | 1,707,706.6 / 1,188,837.3 | 8.4°C | 2.137 |
| NO1, highest low | Jan 22 08:00–15:00 | 2,533,394.2 / 2,984,547.1 | −6.9°C | 1.492 |
| NO5, longest high | Nov 20 15:00–Nov 22 06:00 (39 h) | 744,827.4 / 588,536.6 | 0.6°C | 1.872 |

NO2 matched November 18 and 11, 2021 and January 13, 2022 (daily-mean
temperature differences 0.28–0.56°C). NO1 matched January 5, 2022, January 6,
2021 and December 28, 2022 (0.14–0.36°C). NO5 matched December 24, 2021,
December 22, 2023 and December 10, 2021 (0.01–0.13°C). These comparisons
control only the declared weekday, public-holiday, season and temperature
criteria; they do not prove equivalence or supply fault labels. Holiday-adjacent
behavior and changing aggregate demand can remain unexplained. No incident
confirmation or causal attribution was performed.

Across the 100 reviewable candidates, four NO2 cases had no eligible peers.
Eight DST dates per area were excluded from the historical peer pool. No matching
criteria were relaxed to manufacture comparison days.

## Controlled validation

Five fixed, stationary AR(1) simulations retained both clean controls and identical
copies with predeclared injections. Each has 16 events spread across January,
April, July and October: positive/negative spikes, alternating 48-hour shifts and
six-hour observed-zero episodes. Zero readings are controlled outage-like inputs;
they do not establish the meaning of an observed zero in real data.

| Injection | Detected events | Flagged affected hours | Affected-hour recall |
| --- | ---: | ---: | ---: |
| +6σ one-hour spike | 20 / 20 | 20 / 20 | 100% |
| −6σ one-hour spike | 20 / 20 | 20 / 20 | 100% |
| ±4σ, 48-hour level shift | 20 / 20 | 891 / 960 | 92.81% |
| Six observed zeros | 20 / 20 | 120 / 120 | 100% |

All **80 events** had at least one newly flagged hour relative to their paired
clean control. Four affected hours were already flagged in the clean copies;
1,047 flags were new. Event detection is an any-hit measure and does not imply
complete detection throughout a shift: **69 shifted hours were missed**.

Known no-event controls had **333 false-flag hours / 43,783 scored hours (0.7606%)**,
grouped into **239 false episodes**. Seventeen unsupported-temperature hours were
excluded from scoring. These rates describe only this specified synthetic
generator, not the real population. Per-seed results and non-injected-window
counts are retained; no independence-based confidence claim is made.

A separate six-hour missing-demand copy for each seed left all **30 missing hours
unscored and unflagged**. Changing evaluation-year demand preserved model
selection, coefficients, preprocessing and calibration exactly. Hourly outputs
outside injection windows also remained identical to the paired clean controls.

## Verification

- `python -m pytest -q`: **300 passed**, with two existing dependency
  deprecation warnings. Updated fixture assertions also passed (3 tests).
- Frontend TypeScript and production build passed. Demand-anomaly and sensitivity
  browser journeys passed **4/4**, including URL/history, keyboard tabs, area and
  candidate selection, missing/unsupported data, unavailable studies and exports.
- Actual observed results were inspected on desktop and at 390 px in both themes.
  Mobile legend spacing and table labels were corrected during inspection.
- Independent audit recomputed all five calibration quantile distributions,
  every saved calibration/evaluation score and status, all episode groupings,
  the first 20 peer rankings per area, and every synthetic seed summary. All five
  observed area results replayed **exactly** from the retained CSVs.
- All five area responses worked through the frontend proxy (about 69–82 kB).
  The complete 28.6 MB download matched the stored artifact byte for byte.

## Evidence and replay

The following local, ignored artifacts must be retained together:

- `data/analyses/demand-anomalies.json`: complete observed study and controlled
  validation summaries (28,638,142 bytes).
- `data/analyses/demand-anomalies-evidence/`: frozen protocol, input manifest,
  source archive, execution details, five complete synthetic input CSVs and their
  clean/injected results, and independent audit.
- `data/analyses/demand-sensitivity-inputs/`: exact original observed hourly inputs.

Result SHA-256:
`10a3fd77255831f0fe899cd9776ea83f5cb9341c80bfbaa21faa2c9e1cfa7d29`.
The input manifest remains pinned to
`e8ee286bffea81e9d0d43cb8d2d329c47e22722e4226a6f4564a608abd278de5`.

Run from the repository root with the recorded environment:

```sh
python scripts/run_demand_anomalies.py
```

For a replay, use a fresh output path, for example
`--output data/analyses/demand-anomalies-replay.json`. The companion evidence
folder must also be new. The version-1 synthetic generator implements the exact
frozen equations; it is not a general simulation-configuration interface.
Execution timestamps and compressed source archives can differ across runs;
compare analytical area results and seed results, not the entire artifact hash.

Earlier Step 1, Phase 4, Step 2 and Step 4 result hashes were checked and remain
unchanged. Historical evidence and forecast defaults were preserved. Publishing
requires the separate [release procedure](RELEASE.md); a code push alone does not
publish this local result.
