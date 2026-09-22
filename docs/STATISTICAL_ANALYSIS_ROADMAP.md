# Statistical analysis roadmap

Prepared 2026-09-21 following the project-wide analysis review.

**Status: Steps 0–1 complete and published; Steps 2–7 complete locally on 2026-09-22; Step 8 remains planned.** This document defines the work for step-by-step delivery and records completed checks. It does not authorize executing every step at once. Implementation proceeds in individually selected steps, with results and limitations reviewed before expanding scope.

The goal is to answer useful questions with defensible evidence: what drives observed demand patterns, where forecasts fail, and how much confidence their results deserve. Reuse the current Next.js/FastAPI application and analytical stack. Prefer a small number of understandable studies over more models, pages, or infrastructure.

## Relationship to existing documentation

- [Implementation plan](IMPLEMENTATION_PLAN.md): architecture, migration history, analytical acceptance criteria, and the broader candidate backlog. This roadmap specifies the next statistical work without replacing those historical records.
- [Phase 4 validation](PHASE4_VALIDATION.md): the original forecast protocol, saved results, and limitations. Preserve this evidence and its artifacts.
- [Data pipeline](DATA_PIPELINE.md): source schemas, coverage, time, missingness, and aggregation contracts.
- [UI design](UI_DESIGN.md): visual conventions for integrating results into existing pages.
- [Release operations](RELEASE.md): fixtures, setup, deployment, and rollback.

## Starting point

The app already provides rolling correlation, STL decomposition, spectrograms, weather anomaly flags, regional summaries, and forecast benchmarking. Forecast metrics already include area, season, horizon, and peak-period breakdowns. Three recorded case studies also exist; new work should strengthen the evidence available for those stories rather than duplicate them.

Available inputs include multi-year hourly energy observations across NO1–NO5 and historical weather. Coverage varies by series. Weather uses fixed city proxies rather than area-wide spatial averages. Energy snapshots contain later revisions; weather is reanalysis. Neither reconstructs every historical information vintage.

The original benchmark has four holdout dates per area, with 19 matched area-origins after a failed fit. Its nominal 80% intervals undercovered; gradient boosting achieved 61.6% coverage. These are recorded findings from a small sample, not promises of future performance. The 456 hourly targets per model are not 456 independent experiments. See [the recorded protocol and results](PHASE4_VALIDATION.md#benchmark-protocol).

## Delivery sequence and tracking

The sequence below puts correctness first, then the recommended initial studies. Effort is relative, not a delivery estimate. Independent steps may be selected earlier when useful.

| Step | Deliverable | Dependency | Effort | Status |
| --- | --- | --- | --- | --- |
| 0 | Correct hourly correlation windows and wind-rose sectors | None | Small | Complete 2026-09-21; see completion record below |
| 1 | Weather-adjusted demand sensitivity | Step 0; validated common coverage | Medium | Complete and published; [validation](STEP1_VALIDATION.md) |
| 2 | Broader forecast reliability study | Frozen experiment protocol and eligible data | Medium–large | Complete locally; [validation](STEP2_VALIDATION.md) |
| 3 | Visual forecast-error explorer | Existing saved results; extend with Step 2 later | Small–medium | Complete locally; [validation](STEP3_VALIDATION.md) |
| 4 | Forecast feature ablation | Step 2 evaluation protocol | Medium | Complete locally; [validation](STEP4_VALIDATION.md) |
| 5 | Contextual demand anomalies | Validated expected-demand baseline; reuse Step 1 where suitable | Medium | Complete locally; [validation](STEP5_VALIDATION.md) |
| 6 | Peak demand, rapid changes, and regional synchrony | Validated matched hourly coverage | Small–medium | Complete locally; [validation](STEP6_VALIDATION.md) |
| 7 | Daily demand profiles; optional clustering | Explicit local-day and normalization policy | Medium | Complete locally; [validation](STEP7_VALIDATION.md). Optional clustering omitted |
| 8 | Persistent change and model drift | Adequate historical coverage; Step 2 for forecast-error drift | Medium–large | Planned |

Recommended initial scope: Step 0, then Steps 1–3. Step 3 can be delivered before the larger benchmark finishes because it exposes existing results. Step 7 is now complete; Step 8 is the next candidate.

Update a row only when work starts or its acceptance criteria are met. A study that finds no improvement can still be complete. An optional technique that adds no useful evidence should be omitted with the reason recorded.

## Shared scientific and product requirements

1. **Time and coverage:** retain regular UTC grids and half-open intervals. Use Europe/Oslo for calendar features and clearly labeled local displays. Distinguish elapsed hours, valid pairs, complete days, and missing observations. Never silently replace missing values with zero.
2. **Availability:** forecasting features must be eligible at issue time. Preserve the explicit energy/weather publication-lag assumptions and the retrospective label. Realized future weather remains a separate upper-bound experiment.
3. **Evaluation:** choose preprocessing, features, model settings, calibration, and comparisons before final evaluation. Fit preprocessing within training folds. Record dates and exclusions explicitly. Previously inspected holdout results cannot become untouched evidence again by changing the experiment name.
4. **Dependence and uncertainty:** account for serial dependence and shared regional dates when estimating uncertainty. Specify resampling units and block-length sensitivity where used. Do not treat individual hours as independent, or imply guaranteed interval coverage under unverified assumptions.
5. **Interpretation:** distinguish association from causation, candidate anomalies from faults, retrospective changes from live alerts, and aggregate area behavior from individual behavior. Report unfavorable and inconclusive results.
6. **Reproducibility:** retain source identities, snapshot fingerprints, actual coverage, units, timezone, selected inputs, parameters, splits, exclusions, failures, dependency versions, code revision/source fingerprint, and seeds when relevant. Save enough outputs to recompute reported metrics. Fingerprints identify inputs; exact reruns also require retaining or being able to obtain those inputs.
7. **Minimal implementation:** reuse existing functions, API conventions, charts, exports, and dependencies. Perform analysis before chart downsampling. Run expensive fitting through explicit bounded jobs or offline commands; ordinary page reads should serve prepared results.
8. **Readable presentation:** integrate into existing pages with one primary question and chart per view, concise interpretation, and expandable methods. Support light/dark themes, mobile layouts, keyboard use, non-color cues, and a table or download for important values. Clearly distinguish fixture data from empirical findings.

## Step 0 — Correct analytical foundations

**Scope**

- At review time, [sliding correlation](../app_core/analysis/sliding_correlation.py) dropped missing pairs before applying a row-count rolling window. Preserve a regular hourly grid so a nominal 168-hour window cannot stretch across more than 168 elapsed hours. Keep valid-pair counts distinct from complete rolling windows; the displayed mean remains the mean of valid rolling correlations, not a single correlation over the entire period.
- At review time, [weather exploration](../app_core/analysis/exploration.py) used wind-direction bins starting at 0° with compass labels that conventionally denote centered sectors. Center the 16 sectors on their compass directions and handle the north wrap consistently.

**Acceptance**

- Complete hourly fixtures retain their expected correlation values; internal absent timestamps and explicit missing values do not get compressed into a full window.
- API coverage and window descriptions match the calculation. Lag direction and centered-window behavior remain explicit and tested.
- Wind-rose checks cover 0°/360°, both sides of north, exact sector boundaries, and conservation of counts/shares.
- Relevant correlation, diagnostics API, and exploration tests pass. Historical records are retained; any affected published comparison is explained rather than silently rewritten.

### Step 0 completion record — 2026-09-21

- `rolling_pearson_corr` now reindexes both original series onto their regular hourly overlap before rolling. Missing timestamps and explicit missing values invalidate full windows containing them. Pairwise alignment remains available separately for observed-pair counts and chart normalization. Complete-series values, positive/negative lag behavior, and the existing centered-window convention are retained; the lag helper's contradictory explanatory sentence was corrected.
- The diagnostics API passes the original lagged series into the rolling calculation, returns nulls at unpaired hourly chart positions before display sampling, and counts actual pairs independently of the hourly grid length. Method metadata describes these rules. Enough scattered pairs can still produce zero complete windows: correlations then remain null, never zero. Constant windows also have undefined correlation.
- The exploration wind rose uses compass-centered 22.5° sectors. North spans `[348.75°, 360°)` and `[0°, 11.25°)`; 360° equals 0°. Exact boundaries belong to the clockwise sector. Finite directions in `[0°, 360°]` retain the previous count/share denominator, and no usable directions produces zero counts with null shares.
- Numerical and API regressions cover missing timestamps in either/both series, explicit nulls, missing edges, no overlap, partial-window minimums, independent Pearson calculations for 5/24/168-hour windows, both lag signs, and Oslo DST transitions. Wind tests cover all 16 boundaries, both sides of north, 0°/360°, missing/invalid directions, count/share conservation, and the API output.
- Checks: `.venv/bin/python -m pytest -q tests/test_sliding_correlation.py tests/test_diagnostics_api.py` — **38 passed**; `.venv/bin/python -m pytest -q tests/test_explore_api.py` — **29 passed**; `.venv/bin/python -m pytest -q` — **230 passed**, with two dependency deprecation warnings. `git diff --check` passed. No frontend code changed; no browser or frontend build verification was needed for this step.
- Historical impact: correlations over incomplete input may now be unavailable where the old calculation silently spanned extra hours. Wind-rose sector allocations can change: the 359°/1° fixture now has two north observations instead of one north and one north-northwest. Historical notebooks, validation records, source snapshots, and forecast artifacts were not regenerated or overwritten. The separate snow-drift calculations were not changed.

Step 0 is complete. No additional statistical study, commit, or push was performed as part of this step.

## Step 1 — Weather-adjusted demand sensitivity

**Question:** How does household demand vary with temperature after accounting for calendar effects?

**Scope:** Begin with household demand across NO1–NO5. Compare a calendar-only reference, a linear temperature model, and an interpretable nonlinear temperature response. Use hour, weekday, holidays, and seasonal terms; choose spline complexity and any additional terms on training/validation periods. Resolve overlap between seasonal and temperature signals explicitly rather than interpreting raw correlation as sensitivity.

**Presentation:** Add an adjusted response curve to Patterns, with uncertainty, temperature support/sample density, area comparison, residual diagnostics, and a short explanation of the adjustment. Define which calendar conditions are held fixed or averaged over. Do not extrapolate a confident curve beyond observed support.

**Acceptance**

- Record complete-case coverage and temporal splits; compare held-out errors against both simpler references.
- Verify response extraction against a controlled synthetic relationship and check residual temporal structure.
- Document the uncertainty method and its assumptions; distinguish uncertainty in the estimated mean response from a prediction interval for an individual observation.
- Display units and city-proxy limitations. Call the response an adjusted association, not a causal effect or an operational weather forecast.
- Retain the simpler model if added complexity does not improve useful interpretation or validation.

**Likely integration:** `app_core/analysis/`, `backend/diagnostics.py`, `frontend/app/diagnostics/workbench.tsx`, and Methods & Data. Final module boundaries should follow the implementation rather than create a parallel framework.

### Step 1 completion record — 2026-09-21

The saved five-area study, offline fitting/replay command, read-only API, and Demand sensitivity tab in Patterns are implemented. Calendar-only, linear-temperature, and spline models use chronological selection and evaluation. The interface includes supported mean-contrast bands, temperature support, model/area comparisons, residual diagnostics, accessible tables, and downloads. [The validation record](STEP1_VALIDATION.md) documents the exact protocol, retained inputs, real-data results, 246 passing Python tests, frontend/build/browser checks, and scientific limitations. Step 0 was committed and pushed as `99d587b` before this implementation. Step 1 was initially left uncommitted for review, then committed by the user; the prepared study was published with snapshot update `a7f1857` on 2026-09-21 and verified on the live site.

## Step 2 — Broader forecast reliability study

**Question:** Do model improvements persist across forecast dates, and how reliable are their intervals?

**Scope:** Extend the existing 24-hour household benchmark using configurable origins. First freeze a dated protocol identifying data snapshots, training/validation/calibration periods, embargoes, origin cadence, candidate models, comparison cohort, and a separate final evaluation period. Choose the feasible origin count after a coverage and runtime assessment, before inspecting new scores.

Evaluate substantially more dates across months and seasons where eligible history permits. If available data have already informed model selection, label results exploratory and reserve genuinely uninspected observations for confirmation. Do not manufacture an untouched holdout from previously reviewed dates.

Report paired baseline differences, MAE/RMSE, bias, residual dependence, and existing area/horizon/peak breakdowns. Evaluate coverage with interval width and quantile loss. Begin by assessing the existing interval method; any alternative calibration or quantile model must be selected before final evaluation, with broader pre-holdout calibration support.

**Acceptance**

- A versioned protocol and reproducible command exist before the final run; compute cost is measured on development dates.
- Eligibility, chronological preprocessing, embargoes, and frozen selection/calibration remain verified. Later refits only use observations once eligible.
- Publish attempted, successful, failed, and matched origins, including exclusions by area and date. Show sample support for every displayed breakdown.
- Estimate uncertainty using a method that respects temporal and cross-area dependence; report sensitivity and withhold strong claims when support is inadequate.
- Save new immutable results under a new identity. Preserve `phase4-household-24h` and its validation record.
- Recompute reported scores from saved prediction rows. Poor coverage or no baseline improvement is a valid result, not grounds for tuning against the final holdout.

**Likely integration:** [forecast evaluation](../app_core/analysis/forecast_evaluation.py), [benchmark command](../scripts/run_forecast_benchmark.py), existing forecast artifacts, and a dated validation record.

### Step 2 completion record — 2026-09-22

- Froze a versioned exploratory protocol before score inspection, measured a development-only runtime pilot, retained checksummed hourly inputs and archived the analytical execution sources. The 34.3-minute offline run used 12 validation dates in 2023, 23 calibration dates in 2024 and 46 evaluation dates in 2025 across NO1–NO5.
- Saved a new immutable `step2-household-reliability-20260921` result. It retains 224 matched area-origins (5,376 hourly targets per model), six evaluation exclusions and one calibration failure. The original Phase 4 artifact and evidence are unchanged.
- Added shared-date block uncertainty, signed bias, sample support, calibration residuals and exact-lag residual diagnostics. Forecasts presents the fixed study cohort, uncertainty sensitivity, per-area diagnostics and a complete streamed JSON download. Interactive fitting limits remain unchanged.
- Independently reconciled all 144 metric rows, calibration quantiles, cohort accounting and retained-input hashes: 25,808 checks passed. Deterministic report replay matched exactly. The Python suite passed 265 tests; all five focused Forecasts browser tests, type checking and the production build passed. The real study was also reviewed on desktop/mobile in both themes.
- Gradient boosting's pooled MAE was 16.2% below the seasonal baseline, with 77.9% measured coverage for nominal 80% intervals. Ridge's difference was inconclusive; SARIMAX performed worse. The period was previously inspected, so these remain exploratory findings. Full figures, exclusions, uncertainty and limitations are in [the validation record](STEP2_VALIDATION.md).
- Code and study are complete locally, without commit, push or deployment. Publishing requires an updated serving snapshot as well as code; retained experimental inputs remain separate reproducibility evidence.

## Step 3 — Visual forecast-error explorer

**Question:** Where and when does each model fail relative to the seasonal baseline?

**Scope:** Expose the existing saved area, season, horizon, and peak-period analysis. Add an area-by-model baseline-difference heatmap, forecast-horizon error/coverage curves, and drill-down to saved forecasts. Do not require retraining or fabricate combinations absent from the artifact.

**Acceptance**

- Every plotted value reconciles with saved metrics or an explicitly documented calculation from saved predictions.
- Display the selected cohort, sample counts, units, failed origins, and the direction of improvement. Missing cells remain unavailable rather than zero.
- Distinguish observed coverage from nominal coverage, and label sparse seasonal comparisons as descriptive.
- Filters, drill-down, URL state, and exports remain consistent. Existing recorded artifacts remain readable.
- Check desktop/mobile layouts, keyboard access, both themes, and non-color access to values.

**Likely integration:** `backend/forecast.py` and `frontend/app/forecasts/forecasts-client.tsx`. Reuse existing result contracts where sufficient.

### Step 3 completion record — 2026-09-22

- Added a forecast-error explorer to Forecasts, using saved area, season, peak-period and horizon metrics. The area heatmap shows signed MAE differences from the seasonal baseline; horizon curves show MAE or measured coverage with a separate nominal reference.
- All views explicitly use the full saved matched cohort. Each displayed metric has support counts, older artifacts derive missing support from saved predictions, and missing configured cells remain unavailable in the chart, table and exports. Seasonal comparisons are labeled descriptive.
- Heatmap drill-down opens the saved origin with the largest paired MAE difference versus baseline for an area/model, resetting chart dates and moving keyboard focus. Explorer view and horizon measure persist in URL/history state; exports identify the selected view and cohort.
- Reconciled all 280 breakdown rows from the original and Step 2 artifacts against saved predictions. All eight focused Forecasts browser tests passed, including legacy support, partial data, URL state, downloads and mobile keyboard scrolling. TypeScript and the production build passed; the real study was reviewed at desktop/mobile widths in both themes.
- No model fitting, new dependency, artifact replacement, commit, push or deployment was performed. See [Step 3 validation](STEP3_VALIDATION.md) for definitions, checks and limitations.

## Step 4 — Forecast feature ablation

**Question:** How much predictive value comes from calendar, demand history, and eligible weather?

**Scope:** Compare calendar only; calendar plus demand lags/rolling summaries; and calendar plus demand history plus eligible weather. Use the same model family, origins, availability assumptions, and evaluation policy. Predeclare whether settings are held fixed or each feature set receives the same validation search budget; those answer different questions.

**Acceptance**

- Record exact feature groups and tuning policy. Verify that removing a group removes its derived features too.
- Compare on the same successful origins while retaining all failure records and their effect on cohort size.
- Report changes in error and interval quality with suitable uncertainty; do not infer causal weather effects from predictive value.
- Save each feature-set identity and predictions. No added value from weather is a publishable outcome.

**Presentation:** A compact comparison chart and table within Forecasts, connected to the Step 2 results.

### Step 4 completion record — 2026-09-22

- Froze and ran a ridge-only ablation on the exact retained Step 2 inputs: calendar (9 predictors), calendar + demand (17), and calendar + demand + eligible weather (29), with the same three-alpha validation budget per area/variant.
- All 230 scheduled area-origins were retained with zero failures. Demand history reduced pooled MAE by 7.2%; adding eligible weather increased it by 4.2% and worsened all three quantile losses despite bringing coverage closer to nominal 80%. Findings are exploratory and specific to this ridge specification.
- Saved separate variant results, exact feature identities, source/input provenance, calibration and common-cohort comparisons with paired date-block uncertainty. All 5,376 shared Step 2 ridge targets and interval bounds match exactly.
- Added a compact MAE-bar/table comparison in Forecasts, with signed contrasts, all three block lengths, expandable area scores, exact features and complete artifact download. Verified desktop/mobile and both themes; 289 Python tests, 10 Forecasts browser tests, TypeScript and the production build passed.
- No dependency, commit, push or deployment. See [Step 4 protocol](STEP4_PROTOCOL.md) and [validation](STEP4_VALIDATION.md) for retained evidence, numerical reconciliation and limitations.

## Step 5 — Contextual demand anomalies

**Question:** Is observed demand unusual for its hour, season, and weather?

**Scope:** Build a simple expected-demand baseline and score residual deviations. Reuse Step 1 where validated, but define whether the workflow is retrospective inspection or issue-time detection. Threshold selection and peer-day matching must respect that choice. Show observed/expected demand, ranked intervals, comparable days, and weather/coverage context.

**Acceptance**

- Validate on controlled injected spikes, level shifts, and outages; retain injection definitions and measure detection and false alarms separately.
- Review representative real candidates without treating unreviewed observations as confirmed normal labels.
- Report threshold/calibration support by relevant area or calendar group; avoid unsupported fine-grained thresholds.
- Missing data are handled as coverage issues, not ordinary demand anomalies. Flags remain investigation candidates.
- Preserve existing temperature SPC and precipitation LOF capabilities; this is a distinct demand analysis.

### Step 5 completion record — 2026-09-22

Delivered the frozen retrospective study and **Patterns → Demand anomalies**
for all five areas, including calibrated scores, contiguous candidate episodes,
comparable days, coverage diagnostics and exports. Preserved existing SPC/LOF.
All 80 injected events were detected; known-no-event synthetic controls had a
0.7606% hourly false-flag rate. Real candidate rates range from 0.68% to 2.60%
and have no established fault labels. All five observed results replayed exactly.
See [protocol](STEP5_PROTOCOL.md) and [validation](STEP5_VALIDATION.md) for the
independent audit, limitations, retained evidence and checks. Changes and fitted
results remain local; no publication, commit or push was performed in this step.

## Step 6 — Peak demand, rapid changes, and regional synchrony

**Question:** When is demand highest, how quickly does it change, and do NO1–NO5 peak together?

**Scope:** Add load-duration curves, hour-to-hour demand changes, peak timing, and aligned regional comparisons. Start with household demand and expand only to groups with compatible definitions and coverage. Show absolute magnitude alongside normalized shapes and any seasonally adjusted comparison.

**Acceptance**

- Compute differences only between consecutive observed hours. Explicitly define exceedance percentages, peak selection, ties, and normalization.
- Use matched regional timestamps and report coverage/exclusions; validate ranked curves and peak timing on known fixtures.
- If displaying power, convert hourly energy to hourly average power with explicit units. Do not call it an instantaneous peak or infer grid capacity.
- Do not interpret production minus consumption as measured cross-border flow or attribute co-movement to direct transfers.

**Presentation:** Integrate observed-demand summaries into Explore and aligned area comparisons into Regional; no new top-level page is required.

### Step 6 completion record — 2026-09-22

Added **Explore → Demand peaks** and **Regional → Demand peaks** with exact
load-duration thresholds, consecutive-hour changes, peak timing and aligned
absolute/relative regional curves. Every regional statistic uses the same
complete-case hourly cohort. Zero, missing, invalid, tied and DST cases have
explicit behavior. The views retain one dominant chart, concise metrics and
on-demand details, with no new top-level page or dependency.

The full Python suite passed 315 tests; eight relevant browser journeys passed.
Independent calculations and exact replay validated all five areas on the
retained 2025 snapshot. See [validation](STEP6_VALIDATION.md) for observations,
definitions, coverage and evidence. No commit, push or deployment was performed.

## Step 7 — Daily demand profiles and optional clustering

**Question:** Which daily demand shapes recur across calendar groups and areas?

**Scope:** First deliver weekday/weekend and seasonal hourly profiles with clearly defined distribution bands. Add clustering only if it reveals stable, useful structure beyond those groupings. Compare normalized shape with actual magnitude and show representative observed days.

**Acceptance**

- Document local-day construction and the treatment of 23/25-hour DST days before assembling profiles. Do not silently force them into 24 observations.
- Distinguish between-day variability from uncertainty in a mean. Report complete-day counts and missingness exclusions.
- If clustering proceeds, fit scaling and choose cluster count using development periods; assess seed and period stability on separate data.
- Retain raw-day drill-down and explain that area-level clusters do not identify household types or individual behavior.
- If clustering adds little, finish with interpretable grouped profiles and record the decision.

## Step 8 — Persistent change and model drift

**Question:** Have demand patterns or forecast errors shifted beyond ordinary seasonal variation?

**Scope:** Start with one seasonally adjusted demand series and a simple change-detection baseline. Extend to forecast errors when Step 2 provides sufficient sequential coverage. Choose retrospective segmentation or online detection explicitly before selecting a method; do not present an offline segmentation as an alerting system.

**Acceptance**

- Define the minimum segment length, threshold selection, and treatment of multiple candidate changes.
- Evaluate false alarms on no-change controls and detection behavior on known shifts. Measure delay only for an online procedure.
- Check sensitivity to gaps, revisions, seasonal adjustment, and selected periods. Show before/after effect sizes and supporting observations.
- Annotate coverage changes separately. External events may supply context but do not establish the cause of a detected change.

**Presentation:** A restrained timeline and before/after distributions within Patterns, with Methods & Data explaining the detection policy.

## Deferred work

- **Spatial weather:** investigate multi-location weather and defensible aggregation weights before claiming area-wide exposure. Compare against the city proxy on matched periods.
- **Operational backtesting:** investigate archived issued weather and source vintages. This requires more than changing publication-lag parameters.
- **Prices, reservoirs, and hydrology:** assess source definitions, licenses, coverage, revisions, and alignment before proposing specific studies.
- **Additional model families, reconciliation, and scenarios:** retain the broader candidates in the implementation plan. Prioritize them only when a concrete question and compatible data justify the complexity.

These items are outside the initial sequence. No new provider, dependency, or service is selected by this document.

## Verification and completion record

For each selected step, record the delivered behavior, affected files, actual commands/check outcomes, scientific findings, limitations, and any scope reduction. Add a dedicated validation document when an experiment produces substantial new evidence; link it from this roadmap. Do not duplicate the original Phase 4 record or replace its results.

- Numerical/API changes: run focused tests with deterministic fixtures, then `python -m pytest -q` as appropriate for shared analytical changes. Verify missingness, time boundaries, units, failure behavior, and metric reconciliation rather than only mirroring implementation.
- Frontend changes: run `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`, plus relevant browser journeys for changed interactions. Check real result rendering and clearly labeled fixtures, including mobile and light/dark states.
- Experimental claims: execute the recorded protocol on the named inputs, retain outputs, and independently recompute headline metrics. Passing software tests alone does not validate a scientific conclusion.
- Documentation-only changes: check links and diff consistency; no numerical rerun is required.

Mark a step complete only when its applicable acceptance criteria are met and evidence is linked. Record any remaining limitations explicitly. Commit/push behavior follows the user's instruction for the implementation session; this roadmap does not authorize either action.

## Method references

These references informed the review; implementation must check the APIs supported by the repository's installed versions.

- [Statsmodels generalized additive models](https://www.statsmodels.org/stable/gam.html): interpretable spline-based regression for the sensitivity study.
- [Forecasting: Principles and Practice — time-series cross-validation](https://otexts.com/fpp3/tscv.html): rolling-origin evaluation with chronological training sets.
- [Forecasting: Principles and Practice — bootstrapping time series](https://otexts.com/fpp3/bootstrap.html): preserving temporal structure through block resampling; method assumptions still require assessment.
- [Scikit-learn lagged-feature forecasting example](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html): temporal validation and quantile regression using the existing model stack.
