# Step 8 — Persistent demand changes

## Frozen scope and method

The [protocol](protocols/demand-changes-20260922.json) was frozen before scanning
observed change scores. This is an **exploratory, retrospective NO1 study** of
2025, reusing the saved Step 5 calendar/temperature baseline and 2024 calibration
residuals. The years have been inspected in earlier studies; 2025 is not a new
untouched holdout. No model is fitted by a page request.

A UTC day requires 24 valid hourly observations. Its value is the mean hourly
energy in kWh, not total daily energy or instantaneous power. Incomplete days
remain missing on the calendar grid and split contiguous runs. The primary scan
considers every split with at least 28 complete days on each side within a run.
It retains only the strongest absolute mean-change score, resolving exact ties
by earliest date; there is no recursive search for additional changes.

For each split, the score is `sqrt(nL*nR/(nL+nR))*abs(meanR-meanL)/s_cal`,
where `s_cal` is the sample standard deviation of complete 2024 daily residuals.
The [CUSUM reference](https://www.lancaster.ac.uk/~romano/teaching/2425MATH337/1_intro_cusum.html)
explains scanning for the maximum statistic when the split is unknown.

Calibration globally centers the 2024 residuals and samples wholly complete,
contiguous 14-day moving blocks. Each of 999 draws fills the entire review grid,
then applies its original missing mask and repeats the full eligible-split scan.
The bootstrap tail fraction is `(1 + count(nullMax >= score))/1000`; the frozen
reference decision is at most 0.05. The displayed 95th percentile uses NumPy's
`higher` convention. [Block resampling](https://otexts.com/fpp3/bootstrap.html)
preserves some local dependence, but this does not guarantee calibration under
longer persistence, changing seasons or baseline misspecification.

Controlled validation uses 200 independent calibration/review pairs for each
stationary Gaussian AR(1) coefficient 0, 0.5 and 0.8. Review scenarios share noise
within a pair: no change, July 1 shifts of −2, −1, +1 and +2 population standard
deviations, and a gradual linear rise from zero to +2 SD. Independent random
streams generate the observations and bootstrap draws; per-pair seeds and
results are retained. Report false flags and shift detections with Wilson 95%
intervals, and date localization both among detections and over all trials.
This is offline localization, not alert delay. Controls evaluate the detector,
not uncertainty in the historical baseline fit.

Predeclared sensitivities cover 7/28-day blocks, 14/56-day minimum segments,
Jan–Sep and Apr–Dec windows, two separate fixed seven-day gaps, an additional
2024 monthly residual correction, and ±1% synthetic actual-demand perturbations
from July onward. They are checks, not candidates for picking a better result.
Actual revision vintages are unavailable, so robustness to real revisions is
unverified. Before/after distributions and effect sizes are descriptive,
selected on the same observations; no naive post-selection confidence interval
or causal interpretation is supplied. Gradual drift can also produce a split.

Forecast-error drift is deferred: Step 2 contains 46 origins spaced eight days
apart with 24-hour windows, rather than a continuous daily error sequence.

## Presentation

Patterns gains **Demand changes** with one timeline, an optional before/after
view, concise coverage and a prominent calibration limitation. Numerical values,
sensitivity checks, control results and full provenance are available on demand.
Fixture results are explicitly synthetic. Missing studies, insufficient support
and below-threshold splits have distinct states. The new page uses the existing
design tokens and components with the installed Apple design, interaction,
interface and shadow skills; it adds no runtime dependency.

## Execution and review

The method section above was recorded before executing observed change scores.
The completed execution and review are recorded below.

## Executed observations

The frozen study was executed after protocol and control review. Its source
remains the original Step 5 artifact, unchanged. NO1 has 361/366 complete
calibration days (66 unsupported-temperature hours across five excluded days)
and 365/365 complete review days. The scan evaluated 310 eligible boundaries.

The strongest split starts **2025-11-14**: score **7.73244**, bootstrap 95th
percentile **7.07643**, exceedance estimate **0.022** (21 of 999 maxima at least
as large). Before/after support is 317/48 days. Mean hourly residuals are
49,225.92/165,185.11 kWh, a descriptive difference of **+115,959.19 kWh**
(**1.19760 calibration SD**). This is residual hourly energy averaged over days,
not a daily total or a causal estimate.

The controls **did not achieve the nominal 5% false-alarm target**:

| AR(1) correlation | False flags / 200 | Rate | Wilson 95% interval |
| --- | --- | --- | --- |
| 0 | 17 | 8.5% | 5.37–13.19% |
| 0.5 | 17 | 8.5% | 5.37–13.19% |
| 0.8 | 41 | 20.5% | 15.49–26.63% |

All ±2 SD shifts crossed the reference threshold. At correlation 0.8, −1/+1 SD
shifts crossed in 178/186 of 200 trials; median absolute boundary error among
detections was 12/16 days. Only 99/91 of all 200 trials both crossed and localized
within 14 days. The linear-trend diagnostic crossed in 200/200, 200/200 and
195/200 trials as correlation increased. Thus a crossing cannot establish an
abrupt break. An independent preflight review found a coupled RNG stream in the
initial controls; separate persisted simulation/bootstrap seeds corrected it
before the observed scan and retained control run. No detector setting was tuned
after inspecting these unfavorable results.

The observed finding is also sensitive to the predeclared assumptions:

| Check | Strongest boundary | Bootstrap exceedance | Crosses reference |
| --- | --- | --- | --- |
| 7-day blocks | Nov 14 | .001 | Yes |
| 28-day blocks | Nov 14 | .086 | No |
| 14-day minimum segments | Nov 14 | .024 | Yes |
| 56-day minimum segments | Oct 30 | .047 | Yes |
| Jan–Sep review | Mar 19 | .590 | No |
| Apr–Dec review | Nov 14 | .007 | Yes |
| Remove Mar 15–21 | Nov 14 | .006 | Yes |
| Remove Jul 1–7 | Nov 15 | .117 | No |
| Additional fixed 2024 monthly correction | May 1 | .001 | Yes |
| Synthetic −1% actual demand from July | Nov 15 | .094 | No |
| Synthetic +1% actual demand from July | Nov 14 | .004 | Yes |

These outcomes support an exploratory visualization, not a reliable change
alarm or a claim that a structural break has been established. The UI exposes
both failed calibration and sensitivity near the headline rather than hiding
them in the method disclosure.

## Retained evidence and independent recomputation

The ignored local result is `data/analyses/demand-changes.json`. Its companion
`data/analyses/demand-changes-evidence/` retains the source Step 5 artifact,
frozen protocol, 3,600 control scenario records with seeds, all sensitivity
results, execution context and a source-code archive. Original studies are not
replaced. Publish the artifact through the existing snapshot workflow only when
releasing; a code-only deployment cannot supply this saved study.

| Artifact | SHA-256 |
| --- | --- |
| Saved study | `ed1ac8bc434fdff561555d0ef58d2e1b6568a78fa1f74051332b21ab78e1d90f` |
| Frozen Step 5 source | `10a3fd77255831f0fe899cd9776ea83f5cb9341c80bfbaa21faa2c9e1cfa7d29` |
| Independent audit script | `d6119ceaf23d80181b2f926e4b888006e054a82f0bc39f3090fc7de1adff1d9c` |
| Independent audit evidence | `8c01bfb566e8192b0c014d3b64c833746c6632049728024b0f6371e7a21a558e` |

Run `python scripts/audit_demand_changes.py --output /tmp/step8-audit-new.json`
with a new output filename to independently verify the saved study. The audit
refuses to replace earlier evidence. The audit imports no production analysis helpers: it aggregates hourly
rows with `math.fsum`, evaluates direct segment means instead of prefix sums,
and reconstructs all 999 primary bootstrap maxima and all eleven sensitivities.
All 731 daily rows, coverage, boundaries, statistics and descriptive effects
agree within floating-point tolerance. It also checks all 3,600 control records
and independently aggregates the 18 rate, Wilson and localization summaries.
It does not independently regenerate the AR(1) control simulations.


## Software and interface verification

- `.venv/bin/python -m pytest -q`: **338 passed**, with two existing dependency
  deprecation warnings. The enhanced short-fixture integration check was then
  rerun: **3 passed**, including honest unavailable-study behavior when its
  synthetic calibration lacks complete days.
- TypeScript and the Next.js production build passed using Node 20.19.5.
- Six focused Chromium journeys passed after presentation refinement: saved
  study, below-threshold result, error/retry, unavailable artifact,
  loading/insufficient support, and the actual generated fixture API/download.
  The narrow-width journey checks 320px page reflow and keyboard disclosure use.
- The real observed API returns the saved study (about 191 kB), with no fit or
  upstream call on page reads. The download preserves the saved JSON exactly.
- Independent arithmetic verification is recorded above. Synthetic fixture
  generation was executed; shortened fixtures do not invent observed evidence.

The interface review covered this complete Demand changes flow, not every
existing application page. It used the project's six `better-*` domain owners
alongside Apple design, interaction design and restrained elevation guidance.
The desktop and 320px views were visually inspected in both themes. Existing
spacing, typography and surface tokens were reused; no decorative animation or
new dependency was introduced. Reduced motion remains handled by the shared
chart component. Full assistive-technology and 200% browser-zoom testing were
not performed.

| Domain | Evidence and resolution |
| --- | --- |
| Accessibility | Named controls, native disclosures, numerical alternatives, keyboard activation and a visible focus ring; 320px page reflow passes. |
| Layout | One primary chart; optional distribution view and methods/values behind disclosures. Increased histogram top padding prevents the wrapped mobile legend from crowding the axis label. |
| Writing | Shortened the introduction and finding; calibration failure and sensitivity remain visible. Replaced misleading confirmation language and distinguished resampling calibration from synthetic control evaluation. |
| Typography | Existing type scale, bounded explanatory lines and tabular numerals; long numerical tables scroll inside visibly labeled regions. |
| Color | Both themes inspected. Darkened light-mode candidate/zero reference lines: contrast against white is 3.94:1/5.23:1. Text labels also identify their meaning. |
| UI polish | Reused existing panels, shadows, chart theme, export menu and focus treatment; loading/error/empty states provide explicit feedback. |

Before/after histograms use twelve shared equal-width bins and percentage of
days within each period, with sample counts in the legend. Their heights each
sum to 100%; this avoids confusing unequal 317/48-day sample sizes with a
change in distribution. Full-precision observations and sorted distributions
remain in the JSON, and daily observations can be exported as CSV.

**Completion boundary:** the single-area retrospective demand investigation is
complete locally. False-alarm calibration failed, the selected boundary is
fragile, actual revision robustness is unverified, and forecast-error drift is
deferred for insufficient sequential coverage. These are retained findings and
scope limits, not successful operational detection claims. No commit, push,
snapshot publication or deployment was performed.
