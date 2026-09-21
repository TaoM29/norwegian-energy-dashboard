# Step 1 — Weather-adjusted demand sensitivity

Protocol prepared 2026-09-21 before fitting the new study. **Implemented and locally validated on 2026-09-21.** See the [roadmap](STATISTICAL_ANALYSIS_ROADMAP.md#step-1--weather-adjusted-demand-sensitivity).

## Question and estimand

Estimate an additive association between same-hour historical temperature and aggregate household demand, conditional on calendar controls. This is a retrospective explanatory study using revised energy and reanalysis weather, not an issue-time forecast or a causal temperature effect. Previously available project observations are used; the evaluation period is held out from this study's fitting and selection, but is not claimed to be newly untouched scientific evidence.

The plotted quantity is `f(temperature) - f(reference temperature)` in kWh for an hourly household-demand observation. Calendar conditions cancel in this additive contrast, which assumes the same temperature response across calendar settings. The default reference is 5°C when supported, otherwise a sufficiently supported observed temperature nearest the area's development-period median. A reference must pass the same local-density rule as displayed points; the median itself may fall in a gap. Area curves identify their actual reference and are not directly comparable at different references or demand scales.

## Frozen initial protocol

- Areas: NO1–NO5, consumption group `household`; hourly UTC input grid, no filling or interpolation. The same complete-case rows are used for all model families in an area.
- Training: `[2021-01-01, 2024-01-01)`; validation: `[2024-01-01, 2025-01-01)`; evaluation: `[2025-01-01, 2026-01-01)`, all UTC. Require at least 95% observed demand/temperature pairs per split and explicit minimum sample counts. Record rejected areas instead of inventing data.
- Calendar controls: Europe/Oslo hour and weekday indicators, Norwegian holidays, two annual Fourier harmonics, and a continuous linear trend. The trend extrapolates into later periods; it is an assumption, not an observed future adjustment.
- Candidates: calendar only, calendar plus linear temperature, calendar plus cubic temperature spline with 4 or 6 quantile knots. Ridge penalty 1, intercept unpenalized. Fit knots/scaling on training only. Complexity must improve validation MAE by at least 1% and 0.01 kWh (a numerical floor): six knots over four, linear over calendar, and spline over both simpler families. This rule was fixed before the observed-data run and is retained in artifact metadata.
- Refit coefficients for each finalist family on training plus validation, keeping training-only knots/scaling and selected settings frozen, before evaluating all three on 2025. Evaluation scores never choose the model. Save MAE, RMSE, bias and hourly actual/prediction rows for independent recomputation.
- Restrict the response curve to central development-period temperature support (2nd–98th percentiles) and suppress points with fewer than 30 observations within ±0.5°C. Show a marginal histogram and monthly temperature support. Do not present constant spline extrapolation as observed support.
- Approximate 95% pointwise mean-contrast bands use a ridge-aware HAC sandwich with Bartlett weights over 168 elapsed hours; repeat with 336 hours. Missing hourly score rows stay zero on the original regular grid rather than compressing time. These are conditional on the selected model and omit selection uncertainty, regularization bias, weather-proxy error, omitted-variable bias, and individual-observation variability.
- Refit the selected temperature family with four annual harmonics on development data as a prespecified seasonal-adjustment sensitivity check. Report curve differences rather than selecting controls against evaluation results.
- Evaluation residual diagnostics: bias, lag correlations at 1/24/168 elapsed hours, and means by local hour/month with counts. Remaining structure qualifies the model's adequacy; it is not hidden by a good aggregate error score.

## Reproducibility and delivery

The study is fitted offline by `scripts/run_demand_sensitivity.py`. Ordinary API/page reads only load a saved artifact. `GET /api/diagnostics/sensitivity` omits hourly prediction rows; `GET /api/diagnostics/sensitivity/artifact` downloads the full JSON. Input tables and an execution/source fingerprint accompany the saved study. Existing forecast artifacts and historical validation documents are not regenerated.

With the real published 2021–2025 energy/weather snapshots available:

```sh
.venv/bin/python scripts/run_demand_sensitivity.py
```

The default output is `analyses/demand-sensitivity.json` beside the configured `ENERGY_DATABASE` (normally `data/energy.sqlite`). `DEMAND_SENSITIVITY_ARTIFACT` selects a different saved artifact for the API and CLI default. `--output` chooses a new CLI output without changing the running API. Publication refuses to overwrite an existing result. Retain each result's companion `*-inputs/` directory, which contains exact serialized hourly input tables, checksums, source metadata, and the protocol captured before fitting. Failed attempts retain their inputs; use a new output name when retrying.

Replay the retained inputs without upstream access or refreshed source data:

```sh
.venv/bin/python scripts/run_demand_sensitivity.py \
  --input-dir data/analyses/demand-sensitivity-inputs \
  --output data/analyses/demand-sensitivity-replay.json
```

The replay verifies input checksums and uses the same serialized floats as the original run. The Python environment and source fingerprint remain part of reproducibility; input checksums alone do not guarantee the same implementation.

`scripts/create_fixture.py` also fits a clearly labeled synthetic demonstration from its own 2025 energy/weather observations. Its shorter 60%/20%/20% split and lower minimum counts are recorded explicitly and do not redefine this multi-year observed-data protocol.

The implementation reuses the existing Python statistical dependencies and Patterns page. No automatic retraining or new job service is introduced.

## Recorded results

The final local artifact `data/analyses/demand-sensitivity.json` was generated at `2026-09-21T20:51:36.600281+00:00` from retained inputs. Its base commit is `99d587b`, with uncommitted implementation changes recorded. Source fingerprint: `d1b2d4eaf0a4b108846be23c122eaea5f274a72da92b4eadacb923ceaaea0cd6`. Artifact SHA-256: `b8cc9abbb6c0936f6e37732b69b67efea2c2e7ab3532fa8d92528a7e22685900`.

All five areas have 26,280 training, 8,784 validation, and 8,760 evaluation pairs, matching their expected UTC hours. All use a supported 5°C reference. Errors below are kWh per hourly household observation, rounded for presentation.

| Area | Validation-selected model | Calendar-only evaluation MAE | Selected-model evaluation MAE | MAE reduction vs calendar | Residual lag-1 correlation |
| --- | --- | ---: | ---: | ---: | ---: |
| NO1 | Linear temperature | 169,050.5 | 119,777.0 | 29.15% | 0.945 |
| NO2 | Cubic spline | 97,255.1 | 76,872.7 | 20.96% | 0.948 |
| NO3 | Cubic spline | 64,232.0 | 39,085.1 | 39.15% | 0.942 |
| NO4 | Linear temperature | 46,084.7 | 26,047.8 | 43.48% | 0.959 |
| NO5 | Cubic spline | 41,563.4 | 28,949.6 | 30.35% | 0.947 |

Temperature improves these later-period explanatory errors, but substantial residual dependence and bias remain. The selected models underestimate demand on average in every area; the saved tables retain bias, RMSE, and all three model families. NO1 and NO4 splines have lower evaluation MAE than the selected linear models, but selection is deliberately not changed after seeing that result. These scores are not comparisons against the forecasting seasonal-naive baseline and must not be substituted into the Phase 4 forecast claims.

Changing annual harmonics from two to four changes supported contrasts by at most about 1,434/2,894/1,407/1,639/1,916 kWh for NO1–NO5 respectively. This one sensitivity check does not establish absence of seasonal confounding. The uncertainty bands remain approximate, conditional, and exclude the limitations listed above.

An initial developmental artifact is retained under `data/analyses/development-run/`. Review then corrected unsupported reference selection for separated temperature clusters and excluded suppressed points from seasonal sensitivity. These correctness changes were verified on synthetic controls rather than tuned to observed evaluation scores. The final artifact was fitted from the same retained input tables. An independent full replay in `data/analyses/replay-verification.json` reproduces every area result exactly, including curves, uncertainty, selected models, scores, and predictions; run timestamps and execution metadata naturally differ.

## Verification

- `.venv/bin/python -m pytest -q`: **246 passed**, with two dependency deprecation warnings.
- Numerical tests include an independently generated nonlinear response with seasonal temperature correlation and AR(1) noise, exact UTC-gap handling, no evaluation-driven preprocessing/selection, supported-reference recovery, a hand-computed HAC check, and metric recomputation.
- Every real-data evaluation MAE and RMSE was independently recomputed from saved actual/prediction rows. Exact retained-input replay passed for all five areas. The final replay-based fit took about 1.90 seconds locally with single-threaded numerical libraries; this excludes initial snapshot loading and is not a deployed latency claim.
- API tests verify saved-only reads, unavailable/corrupt artifacts, fixture identity, full-evidence downloads, and non-overwriting publication. Offline fixture generation includes a fitted sensitivity result for all five areas.
- Frontend generated-route TypeScript checks and production builds passed. Four focused Playwright journeys passed: sensitivity URL/area/history/keyboard/download behavior, unavailable-state retry, existing diagnostic draft behavior, and existing analysis/regional workflows.
- Native browser inspection used the real artifact at desktop and 390px mobile widths in light/dark themes. Curves, negative-valued uncertainty bands, area switching, and support tables rendered. Mobile document width remained 390px. The four method tabs now wrap so the selected sensitivity tab stays visible. An unused ECharts graphic option found during inspection was removed.
- `git diff --check` passed. No new dependencies, background service, source refresh, or Step 2 experiment were introduced.

**Step 1 is complete locally.** Code and artifacts remain uncommitted for review. The public deployment still uses its existing pinned data archive; including this study in a future release requires the normal snapshot publication workflow. The packaging script includes the prepared default study when present.

Subsequent publication, 2026-09-21: after the user committed the implementation,
snapshot update `a7f1857` published the unchanged study to production. All five
areas, the rendered response chart and the downloaded artifact checksum were
verified through the dashboard domain. The earlier completion statement above
records the state at the end of implementation.

## References

- [SplineTransformer](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.SplineTransformer.html): fitted knots and extrapolation policy.
- [Statsmodels HAC covariance assumptions](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html): equally spaced observations; the study implements the ridge-aware contrast calculation rather than substituting ordinary OLS covariance.
- [Time-series cross-validation](https://otexts.com/fpp3/tscv.html): chronological evaluation principles.
