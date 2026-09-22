# Step 5 — Contextual demand anomaly protocol

Frozen on 2026-09-22 before fitting or inspecting new candidate scores. Exact
settings and injections are in [the JSON protocol](protocols/demand-anomalies-20260922.json).

This is **retrospective inspection**, using same-hour realized temperature and
revised household demand. A flag is an investigation candidate, not a confirmed
incident, causal attribution or issue-time alert. Prior studies already inspected
2025; no untouched confirmation is claimed.

## Model and chronological boundaries

Reuse Step 1's calendar/temperature basis and validation selection rule, with a
new chronological split. Its saved final coefficients included 2024 and therefore
cannot supply independent 2024 threshold calibration.

| Stage, UTC bounds | Purpose |
| --- | --- |
| 2021–2022 | Fit preprocessing and candidate coefficients |
| 2023 | Select calendar, linear temperature or 4/6-knot spline using the original 1% and 0.01 kWh improvement rule |
| 2021–2023 | Refit selected coefficients; preprocessing stays frozen |
| 2024 | Calibrate signed residual thresholds and median correction |
| 2025 | Score and review without refitting or adjusting thresholds |

Keep ridge penalty 1, unpenalized intercept, Oslo hour/weekday, Norwegian holidays,
two annual harmonics and linear trend. Step 4 used lagged issue-time weather;
this distinct retrospective task uses contemporaneous temperature. Its results
must not be substituted into forecasting claims.

Read the retained Step 1 hourly CSVs with checksum verification and round-trip
float precision. Pin manifest SHA-256
`e8ee286bffea81e9d0d43cb8d2d329c47e22722e4226a6f4564a608abd278de5`.
No upstream refresh, interpolation or replacement of missing values is allowed.
Require 95% paired coverage in each stage and the minimum counts in JSON.
Calibration additionally requires 8,000 supported hours and 300 UTC dates.
Temperatures outside the observed development range remain unsupported and
unscored; missing demand/weather remain coverage issues. Degenerate calibration
tail widths make the area unavailable rather than producing arbitrary scores.

## Scores, episodes and comparable days

For each area, freeze 2024 residual quantiles at 0.5%, 50% and 99.5%. Display
`expected = raw model estimate + median residual`. The reference envelope remains
`raw estimate + lower/upper residual quantiles`. Divide positive deviations from
corrected expected by the upper tail width and negative deviations by the lower
tail width. Flag only scores strictly greater than one. A score is neither a
probability nor a confidence level, and this empirical calibration envelope does
not guarantee 99% future coverage. Report calendar-group support and exceedance
rates descriptively, without fitting sparse group-specific thresholds.

Group consecutive flagged UTC hours with the same sign into episodes. Any gap,
unsupported observation, unflagged hour or sign change breaks an episode. Rank by
peak score and timestamp, without a minimum-duration filter. Save all rows and
episodes; the interface reviews the top 20 with hourly context around each peak.

Comparable days come only from complete pre-2025 Oslo local dates with 24 hours,
the same weekday and holiday status, circular seasonal distance no greater than
45 days and mean temperature within 3°C. Choose up to three by temperature
distance, seasonal distance and recency. Never match on demand or residuals.
Report excluded 23/25-hour DST dates and unmatched cases; do not relax the rules.
Comparable days are observations, not verified normal controls.

## Controlled validation and real review

Use five fixed seeds, 20260922–20260926, with a known positive calendar-plus-linear
temperature demand mean and stationary AR(1) demand noise (rho 0.8, marginal
standard deviation 30 kWh). Temperature has seasonal/daily terms and independent
AR(1) weather variation. Exact equations and parameters are frozen in JSON.

Preserve clean controls and copies with identical background observations. For
January, April, July and October 2025, inject a +6-sigma one-hour spike on the
10th at 12 UTC, a −6-sigma spike on the 12th at 12 UTC, a 48-hour ±4-sigma shift
from the 15th at 00 UTC, and six observed zeros from the 21st at 00 UTC. Shift
signs alternate positive/negative across the four months. This gives 80 events
across five seeds. A separate copy replaces six hours on November 10 with missing
demand; these must have null scores and break episode continuity.

Report clean-control false flags and false episodes separately from injected
event any-hit recall, affected-hour recall and flags outside injected windows.
Keep all seeds, denominators and unscored hours; never tune thresholds, amplitudes
or event times after observing results. Synthetic false alarms have known labels;
real 2025 observations do not. Review representative high, low and long-duration
real candidates using coverage, temperature and peer context without inventing
normal or fault labels. An observed zero is not proof of a real outage.

## Delivery and evidence

Fit offline with `scripts/run_demand_anomalies.py`. Preserve protocol, input
manifest, source archive, complete calibration/scoring rows, synthetic controls
and injection definitions, and an immutable result. Page/API reads never fit.
Patterns gains a separate **Demand anomalies** view; existing temperature SPC
and precipitation LOF remain available. Downloads retain the complete evidence.
Publication follows [release operations](RELEASE.md); local fitting does not
update the public site.
