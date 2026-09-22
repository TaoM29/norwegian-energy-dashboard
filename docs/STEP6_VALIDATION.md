# Step 6 — Peak demand, hourly changes and regional synchrony

## Scope and definitions

This descriptive analysis uses published **household consumption** observations.
It does not add another fitted model, scheduled job, external source or page.
Explore gains **Demand peaks**; Regional gains a separate household comparison.
Existing energy, weather, map and snow workflows remain available.

All calculations use the original hourly data before chart rendering. API
intervals are UTC `[start,end)` and bounded to 366 days. Date-picker end dates
remain inclusive and are converted to the next midnight when querying. Charts
use UTC; peak labels explicitly use Europe/Oslo. DST does not change elapsed-hour
differences or collapse repeated local hours.

- **Usable observations:** finite nonnegative kWh with source quality `ok`.
  Missing, negative, nonfinite and invalid-quality values remain excluded; zero
  is observed energy, not a missing-value substitute. Duplicate or off-hour
  records and incompatible units are rejected instead of silently aggregated.
- **Load-duration curve:** descending distinct demand values. At each threshold,
  the horizontal coordinate is `100 × count(value >= threshold) / usable hours`.
  Equal values share the same inclusive percentage; the denominator excludes
  missing hours. This is an empirical distribution of the selected observations,
  not a future exceedance probability. All threshold values are exported.
- **Peak:** maximum hourly energy with earliest UTC occurrence and exact tie
  count. This is not instantaneous power, grid capacity, or an independent event.
- **Hourly change:** current minus previous hourly energy, only when both hours
  are consecutive and usable within the selected interval. A missing hour breaks
  the difference. The largest rise must be positive; the largest fall must be
  negative. Absent directional changes return unavailable, not invented zeros.
- **Regional comparisons:** all five areas share exactly the same usable
  timestamps. Missing data in any area exclude that timestamp from every
  regional statistic and leave a visible gap in each aligned series. Coverage
  lists both area-specific observations and the shared denominator.
- **Relative shape:** `100 × hourly demand / that area's mean over shared hours`.
  An area whose shared mean is zero has no defined relative curve; its absolute
  observations remain available. No seasonal adjustment is performed.
- **Coincident peak:** maximum sum of the five areas at one shared hour. The
  coincidence factor is this sum divided by the sum of each area's separate
  maximum on the same shared cohort. A zero denominator returns unavailable.
  It describes coincidence of observed household demand, not usable grid capacity.
- **Correlation:** descriptive Pearson correlation on those same shared hours;
  fewer than two pairs or a constant series returns unavailable. Common season,
  calendar and other influences remain; correlation does not establish transfers,
  causation or independent evidence.

## Presentation policy

Keep one principal chart in view, a short interpretation and a small set of key
values. Reuse date/area controls, hide irrelevant energy-group and weather
settings in these modes, and put numerical detail and method definitions behind
explicit disclosures. Consolidate exports. Support visible coverage and empty
states without presenting a long methodology essay above the chart.

## Observed-data check

The local 2025 snapshot was inspected on 2026-09-22. Each area had **8,760 usable
hours** and **8,759 valid adjacent pairs**, with no exclusions. Regional statistics
used all 8,760 shared hours. These are descriptive results for this retained
snapshot and interval; changing dates or publishing revised data can change them.

| Area | Peak hourly energy, kWh | Peak hour, UTC | Largest rise, kWh | Largest fall, kWh |
| --- | ---: | --- | ---: | ---: |
| NO1 | 3,809,860.8 | Jan 5, 16:00 | +280,885.5 | −237,395.2 |
| NO2 | 1,996,923.6 | Dec 24, 15:00 | +295,386.1 | −160,417.2 |
| NO3 | 1,318,900.6 | Jan 6, 16:00 | +97,782.9 | −120,225.0 |
| NO4 | 965,582.0 | Dec 31, 16:00 | +76,095.6 | −51,248.7 |
| NO5 | 802,213.6 | Jan 11, 17:00 | +64,105.2 | −49,717.2 |

The combined highest hour was **8,644,770.15 kWh at January 5, 16:00 UTC**.
The sum of the separate area maxima was 8,893,480.6 kWh, giving a coincidence
factor of **97.20%**. Each area's maximum occurred at a different timestamp;
nearby demand levels can still produce a high coincidence factor. Raw matched
correlations ranged from 0.9137 to 0.9906. Neither this factor nor these
correlations establish grid capacity, energy transfers or causal relationships.

## Verification and retained evidence

- Full Python suite: **315 passed**, with two existing dependency deprecation
  warnings. Fifteen focused Step 6 tests cover ties, exact duration ranks,
  invalid-quality/nonfinite/negative/missing hours, zero and constant values,
  one-hour and one-direction samples, UTC adjacency through both Oslo DST
  changes, exclusive boundaries, regional matching, undefined correlations,
  snapshot consistency and API range limits.
- Frontend TypeScript and production build passed. **Eight browser journeys**
  covered the new modes plus existing Explore/Regional navigation, date filters,
  exports and styled controls. The new checks assert inclusive picker dates map
  to the exclusive API boundary, chart/scale switching, browser history and
  keyboard tab navigation. Real 2025 results were inspected in light/dark themes
  on desktop and at 390 px; no horizontal overflow was found.
- The one-year NO1 and regional API responses matched the retained evidence
  exactly (1.43 MB and 0.97 MB respectively). Both remain below the platform
  buffered-response limit; no chart sampling alters any statistic or export.
- Independent calculations reconciled every duration threshold and hourly
  difference for all five 2025 areas, their peaks and tie counts, the regional
  cohort, coincidence factor and all ten Pearson correlations. Relative curves
  average to 100 on the matched cohort. All analytical results replayed exactly
  from retained round-trip CSV inputs.

Local audit evidence is retained in
`data/analyses/step6-demand-peaks-20260922/`: five input CSVs with source-version
metadata and SHA-256 fingerprints, all five area responses, the regional
response, calculation/API source copies, execution context, and the independent
`audit.py` / `audit.json`. The directory is ignored like other local analysis
evidence. The audit can be rerun from the repository environment with:

```sh
python data/analyses/step6-demand-peaks-20260922/audit.py
```

This feature computes bounded descriptive summaries from the selected published
energy snapshot on request. It does not require an offline model fit or a newly
published study artifact. The SHA-256 checks for Step 1, original Phase 4, Step 2, Step 4 and Step 5
artifacts were unchanged. No commit, push or deployment was performed.
