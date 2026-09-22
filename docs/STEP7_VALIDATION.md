# Step 7 — Daily demand profiles

## Scope and calculation policy

Explore gains **Daily profiles**, using published household consumption for one
price area and the existing UTC date selection. This is a descriptive view of
area totals, not a household classification, forecast or causal analysis.
The following policy was fixed before inspecting the observed-data results.

- Requests use UTC `[start,end)` intervals, bounded to 366 elapsed days. The
  inclusive date-picker end becomes the next UTC midnight. Calendar grouping
  uses **Europe/Oslo**; profile hours are local hours, not UTC hours.
- Construct each touched local day from its actual local midnight boundaries.
  A day must be entirely inside the requested interval, contain 24 elapsed
  hours, and have 24 usable observations to enter a profile. Partly selected
  boundary dates and the 23/25-hour daylight-saving dates are excluded from
  the 24-hour comparison, never padded, averaged or interpolated into it.
- Usable observations are finite, nonnegative hourly kWh with source quality
  `ok`. Duplicate timestamps, timestamps off the hourly grid and incompatible
  units are errors. Missing or invalid observations remain missing.
- All touched days remain available for observed-day inspection, including
  excluded days. Raw rows preserve UTC timestamps and Oslo offsets, so the
  repeated autumn hour remains two distinct observations. A boundary-day
  drill-down contains only hours inside the selected interval.
- Actual profiles use hourly kWh. Relative profiles first divide each day's
  observations by that day's own mean and multiply by 100, then summarize
  across days. Thus 100 means the day's average hourly demand. An all-zero day
  contributes to the actual profile but cannot contribute to the relative
  profile. Relative profiles describe shape rather than demand magnitude.
- Each local hour shows the median and linearly interpolated empirical 10th
  and 90th percentiles across eligible days in its group. These are
  **between-day variability bands**, not uncertainty in an estimated mean or
  a prediction interval. Bands require at least five eligible days; a median
  can be shown for a smaller group with its count visible.
- Weekdays are Monday–Friday, including public holidays; weekends are Saturday
  and Sunday. Seasons pool all selected December–February (DJF), March–May
  (MAM), June–August (JJA), and September–November (SON) dates. Groups are
  unadjusted mixtures of weather, holidays and other conditions; differences
  do not identify individual behavior or a causal calendar effect.
- A representative day is the eligible positive-mean observed day with the
  smallest squared distance from its group's 24 hourly relative medians.
  Ties select the earliest local date. This is a descriptive example chosen
  from the same data, not a held-out validation case. Arbitrary observed days
  remain selectable so the representative is not the only accessible evidence.

Clustering is omitted. The requested calendar comparisons provide interpretable
groups without fitting or tuning another model. No cluster stability experiment
was performed, and no claim is made that clustering was tested and failed.
Adding it later requires a concrete additional question, development-only
scaling and model selection, and separate period/seed stability evidence.

## Presentation and reproducibility

Use one main chart, compact group/scale controls, short visible interpretation
and coverage, and disclosures for observed days, numerical values and methods.
Retain light/dark themes, keyboard use, narrow-screen reflow and fixture labels.
Existing components, chart exports and design tokens take priority over new
dependencies. The owner's four requested UI skills are linked from AGENTS.md;
their [pinned sources and licenses](../.agents/skills/UI_SKILL_SOURCES.md) are
retained with the project.

These are bounded calculations over the published energy snapshot, so ordinary
page reads need neither an offline fit nor a new study artifact. The response
records the input fingerprint, source version, time policy, coverage and
calculation definitions. Day-exclusion categories can overlap; zero-mean days
are excluded only from shape. Counts should not be added into a single total.

## Observed-data check

The local 2025 UTC snapshot was checked on 2026-09-22. Each of the five areas had
8,760 usable hours, touching 366 Oslo dates. The selection contains 364 whole
local days; removing the two DST dates leaves **362 eligible days**, comprising
260 weekdays and 102 weekend days. Two partial boundary dates remain available
for inspection. There were no incomplete or zero-mean days in this selection.
Seasonal counts were winter 89, spring 91, summer 92 and autumn 90.

| Area | Representative weekday | Representative weekend | Weekday median peak, Oslo hour | Weekend median peak, Oslo hour |
| --- | --- | --- | --- | --- |
| NO1 | 2025-01-30 | 2025-02-23 | 20:00 | 19:00 |
| NO2 | 2025-04-22 | 2025-01-26 | 20:00 | 19:00 |
| NO3 | 2025-01-28 | 2025-06-08 | 21:00 | 19:00 |
| NO4 | 2025-10-23 | 2025-02-01 | 20:00 | 20:00 |
| NO5 | 2025-11-24 | 2025-02-23 | 21:00 | 20:00 |

These peak hours belong to the **hourly kWh median profile**, not the
representative day's peak or the largest individual hour in the year.
Representative selection uses normalized shape. These summaries describe the
retained snapshot and selected period; they are not future-behavior claims.

## Verification and retained evidence

- The full Python suite passed **326 tests** with two existing dependency
  deprecation warnings. Eleven focused profile checks cover both DST changes,
  partial boundaries, missing/invalid/negative/nonfinite observations,
  zero-mean days, percentile support, representative selection, stable input
  fingerprints, malformed sources, endpoint provenance and bounded requests.
- An independent calculation reconciled **43,800 selected hourly observations**,
  every raw day, exclusion, group count, hourly median/percentile and
  representative. Independent calendar arithmetic uses Python `zoneinfo` and
  a separate order-statistic calculation. Analytical responses and input
  hashes replayed exactly from the retained round-trip CSVs.
- Each complete-year response is about **1.08 MB**. The API serves the same
  calculation for fixture and observed snapshots and labels its data mode.
- Historical Step 1, Phase 4, Step 2, Step 4 and Step 5 result hashes were
  unchanged before and after capture.
- TypeScript and the production build passed. Seventeen relevant browser
  journeys passed across the profile, peak and date-filter suites. The four
  profile journeys cover UTC boundaries/history, group and scale selection,
  repeated DST offsets, disclosures, exports, empty/loading/error/retry states,
  an unmocked fixture API response, keyboard focus, reduced motion and 320 px
  light/dark reflow. A downloaded PNG was inspected for axes, legend and scope.

### Interface review

Scope: the new Explore daily-profile flow, using existing React, CSS tokens,
Radix controls and ECharts. Guidance inspected: AGENTS.md, UI_DESIGN.md,
dashboard-ui/motion and the four requested skills with Better Interface's six
domain owners. This is not a review of every existing dashboard screen.

| Domain | Evidence inspected | Result |
| --- | --- | --- |
| Accessibility | Named controls, native disclosures, keyboard representative selection/focus, scrollable tables, reduced-motion rule; browser empty/loading/error/retry journeys | No remaining actionable finding in these checks |
| Layout | Real 2025 results at 1280 px and 320 px, both themes; default-closed tables and responsive controls | No page overflow; representative heading stays below sticky toolbar |
| Writing | Labels, UTC/local-day distinction, exclusions, variability-versus-uncertainty copy and recovery instructions | No remaining actionable finding |
| Typography | Rendered headings, wrapping, table numerals and chart labels | Readable hierarchy; chart ticks avoid overlap on narrow screens |
| Colors | Rendered light/dark text/background pairs and chart swatches; calculated contrast | Muted text 5.52:1 light / 7.39:1 dark; action text 6.02:1 / 7.23:1. Summer line corrected from 2.23:1 to 3.94:1 against the light panel |
| UI polish | Shared surfaces, theme-matched legend, focus outline, representative jump, chart PNG and disclosures | No new runtime dependencies; restrained existing elevation retained |

Findings addressed: summer-line contrast, a representative jump hidden by the
sticky toolbar, repeated coverage counts, unavailable exports in empty states,
and a chart download without a standalone legend/scope. Hover feedback uses the
existing accent-hover color rather than fading the text below its contrast
target. Detailed review did not justify decorative animations or extra panels.

**Not verified:** a manual assistive-screen-reader session, native browser 200%
zoom, RTL/localization and forced-colors mode. The browser checks cover 320 px
reflow and accessible names/focus; they are not a complete accessibility audit.
**Verdict: Approve for the inspected scope.** No unresolved blocking finding was
identified in that scope.

Retained local evidence is in
`data/analyses/step7-demand-profiles-20260922/`: five input CSVs, five complete
API responses, source copies, a manifest of source/input/output fingerprints and
execution context, and the independent audit and its results. Like other local
data evidence, this directory is ignored. Re-run its check with:

```sh
python data/analyses/step7-demand-profiles-20260922/audit.py
```
