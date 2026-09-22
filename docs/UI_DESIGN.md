# Portfolio UI refresh

Implemented 2026-09-15. The interface supports two levels of reading: a visitor can understand the energy overview and follow a question; an analyst can reach detailed controls, source values, exports and methodological limits.

## Readability as features grow

Keep the main reading path light: a clear question, a dominant chart, a few useful
values and one short interpretation. New analytical features should occupy a
focused view within an existing workspace rather than accumulate panels on its
default screen. Show only controls relevant to the current task; reuse shared
filters and combine related downloads in one Export menu.

Use generous spacing and a clear visual hierarchy. Keep methods, long tables,
source metadata and secondary comparisons available on demand. Units, applied
scope, missing-data notices and limitations needed to interpret the visible
result must remain visible. Review each addition in desktop/mobile and both
themes, asking whether a first-time reader can understand the chart without
working through paragraphs of text or a row of competing buttons.

## What changed

- A persistent desktop sidebar groups the six pages into Workspace, Analysis and Project. A slim top bar keeps the current page and theme controls visible; mobile uses a compact Menu button with all destinations available on demand, Escape dismissal and focus return.
- The overview opens with compact metrics and the main supply/demand chart, followed by equal-duration period comparison, production mix, the sortable five-region consumption table and guided findings. Region details open in a right-hand drawer with energy totals, generation mix and source coverage for the selected dates. Inspecting a region keeps the current overview intact until “View this region” is selected.
- Light and dark themes, with dark as the default. Older system preferences resolve to dark. The explicit preference persists across visits; charts, tooltips and PNG backgrounds follow the active theme. Theme changes update chart styles without recreating the chart instance.
- A plain-language overview introduction, optional short reading guides and three pathways into exploration, forecasting and project methods.
- Diagnostic choices describe the question first. Model parameters sit under “Method settings”; keyboard arrows move between choices.
- The explorer starts with daily summaries; explicit hourly/weekly URL selections still work. Line opacity is under “Display options”. The underlying aggregation rules, source values and exports are unchanged.
- Neutral charcoal and light surfaces, compact pill controls, subtle row dividers and restrained hover/press feedback. Theme changes apply immediately without color transitions. The detail drawer supports Escape, focus return and keyboard opening without motion. Reduced-motion preference removes those transitions. No animation framework or runtime dependency was added.

## Date and filter interaction follow-up

- A shared range picker serves overview, exploration, regional analysis, patterns, forecast targets and SARIMAX training. It has two calendar months on desktop, one on mobile, typed entry, validation, Cancel/Escape and focus return. Shortcuts use available observations rather than today's date; forecast calendars mark saved targets.
- Displayed ranges include both dates in UTC; backend requests retain their exclusive end boundary. Analytical forms stage changes until Apply/Run, show applied scope and pending state, and offer Discard changes. Patterns retain previous results while editing and label them using their applied settings.
- Navigation follows applied observation filters through Back/Forward and reload. Forecast dates remain separate from the observation workspace. Live forecast filters replace the current history entry; opening a result creates an entry. Narrowing targets selects a compatible saved origin.
- Forecast evidence labels wrap into two columns at medium desktop widths. Regional groups use wrapping checkbox choices instead of a clipped multi-select requiring modifier keys. Forecast chart and metric notes explain each output's filter scope.
- The picker follows the [shadcn/ui composition](https://ui.shadcn.com/docs/components/radix/date-picker), using React DayPicker and Radix Popover with project-owned markup and styling.

## Results-first workspaces and guided findings

- Forecasts start with the saved result selector, a summary of average error against the seasonal baseline and observed interval coverage, then the primary chart. The summary uses overall rows for selected models/cohort, rejects ambiguous model rows and mismatched sample counts, and labels retrospective evidence. Detailed metrics, training diagnostics and availability assumptions remain in disclosures.
- Experiment settings open in a right-side native dialog, with one experiment form at a time and collapsible job history. Jobs, cancellation and result opening remain available. Nested calendar/export popovers stay inside the modal layer so they remain interactive.
- Regional has distinct Energy comparison and Snow model tabs, with only the active task's controls, requests and outputs. URL mode survives Back/reload; legacy snow links still select the model. Snow seasons are independent of energy date ranges.
- Chart image, data and metadata downloads share an Export control next to the result. Overview exports and table exports use the same pattern. Plain-language labels explain smoothing, shape comparison and energy units without changing calculation or exported units.
- Overview compares consecutive equal-duration UTC windows using the existing endpoint. Deltas are withheld for incomplete observations, zero baselines have no percentage, unavailable prior coverage is explained and snapshot changes prevent mixed-snapshot comparisons. View previous period participates in browser history.
- Three guided cases reuse the recorded production/consumption, forecast benchmark and Bergen snow evidence. Overview and Methods share one component, with reproducible links, snapshot/fixture caveats and source validation references. Recorded findings remain separate from the current filters.

## Styled controls and contextual explanations

- All application dropdowns and calendar month/year controls use one styled Radix Select composition, with theme tokens, selected indicators, keyboard navigation and typeahead. Empty job selections remain supported; select popovers inside native dialogs stay in the modal layer.
- Short secondary explanations use HelpTip, available on hover, keyboard focus and click/tap. Longer reading guides, source notes and method/provenance explanations open in HelpPanel drawers. Errors, partial-data status, units, applied filters and scientific warnings stay visible. The generic source footer is now an explanation control.
- SARIMAX setup starts with training dates, time unit, ahead horizon and energy availability delay. Hourly presets are 24/72/168; daily presets are 7/30/60. A three-step timeline shows inclusive training dates, issue/start after the delay, and the exclusive boundary after all forecast targets. Advanced model structure, weather inputs and rolling backtests remain accessible in closed sections.
- The forecast timeline follows the backend: issue = exclusive training end + energy lag; window end = issue + horizon × target duration. The shared calendar uses UTC-aware dates for custom month navigation, avoiding browser-timezone month shifts.
- Browser checks cover native-dialog nesting, selector keyboard/focus behavior, help activation/dismissal, calendar month offsets and a 72-hour forecast-window/submission check in addition to existing analytical journeys.

## Reference-led visual refinement — 2026-09-21

The two supplied dashboard screenshots informed a quieter, more spacious treatment: layered charcoal surfaces, restrained colour accents, clear metric hierarchy and subtle panel boundaries. The light theme uses the same structure with soft grey surroundings and white panels.

- Centralized sidebar width, panel/control radii, shadows and system typography in the theme tokens. Removed duplicate analysis layout rules so the shared shell governs every page.
- Increased small overview labels, navigation and key values; gave metrics separate cards with semantic icon accents. Energy balance keeps its calculation and exports caveat visible.
- Grouped overview help/export actions in the heading. Standardized control geometry, table spacing, result panels and disclosures across the analytical pages.
- Kept production green and consumption amber in the overview; added a restrained fading chart fill and theme-aware generation-mix colours. ECharts now uses the app's system font and remaps the previously unhandled brown series in dark mode.
- Retained data queries, calculations, chart axes, exports, fixture labels, URL state, theme preferences and keyboard/reduced-motion behaviour. No dependencies were added.

Validation: TypeScript checking, production build and all 18 offline Chromium journeys passed. Desktop dark/light and 390px mobile layouts were visually inspected. Checked main text, muted text, links and primary-button token pairs exceed 4.5:1 contrast in both themes; this is a focused colour check, not a claim of a full accessibility audit.

## Forecast reading and reliability — 2026-09-21

The forecast page groups controls with the chart and uses a shorter heading and an unboxed result selector. The saved summary identifies the full evaluation cohort, matched area-origins and observations per model, and labels observed coverage below its nominal target. Area, dates and origin affect the chart; cohort and model selection also determine the overall summary.

Model colors remain stable across selection changes. A wrapping HTML legend replaces the paginated canvas legend, and an explicit interval-model selector defaults to the best-MAE selected model with stored bounds. Tooltips report lower and upper bounds; the expandable forecast table exposes the same filtered values with UTC timestamps and kWh units. PNG exports retain a title and canvas legend, including the selected interval band.

The first metric table focuses on MAE, baseline comparison, coverage and sample size. “All metrics” retains RMSE, MASE, width and every quantile loss; downloads and scientific artifacts remain unchanged. Public deployments replace the unavailable experiment action with local setup guidance. Result-load errors cannot show an old artifact under a different selection and offer retry; job-history failures do not block saved results.

Verification included production compilation and TypeScript checks, the existing browser journeys, focused failure/retry and interval-bound regressions, keyboard table scrolling, mobile overflow checks, desktop light/dark and 390px visual inspection, and inspection of a downloaded PNG.

## References and selection

Reviewed [Beautiful UI](https://www.beautifului.dev/), [beUI’s catalog](https://beui.dev/llms.txt), [Rare UI](https://www.rareui.com/), [Transitions.dev](https://transitions.dev/) and [shadcn/ui](https://ui.shadcn.com/docs/components). Applied the ideas of clear navigation, compact selection controls, optional detail and restrained state feedback. The existing shadcn-style buttons/cards and native disclosures were sufficient; no third-party component source was copied.

The supplied CRM screenshots informed the compact workspace structure, neutral selected rows, small badges and detail drawer. Applied [Emil’s design engineering skill](https://www.skills.sh/emilkowalski/skills/emil-design-eng) and [better-ui](https://www.skills.sh/jakubkrehel/skills/better-ui) for surface hierarchy, interaction feedback and restrained motion. The drawer uses native dialog behavior for focus and dismissal. Styled selectors follow the [official Radix Select API](https://www.radix-ui.com/primitives/docs/components/select), using project-owned markup and styles.

## Verification

TypeScript and production builds pass. Eighteen Chromium journeys cover the existing analytical routes and downloads plus independence from device theme changes, saved preference across navigation/reload, 390px layouts, reading guides, hidden/revealed settings, keyboard method selection reduced-motion mode, region sorting and keyboard drawer dismissal/focus return. Additional checks cover range validation, inclusive UTC dates in a non-UTC browser, cancellation/focus return, mobile selection, staged filters, navigation history and compatible forecast origins. The additional journeys verify grouped downloads, equal-period changes and incomplete-data suppression, independent regional requests, modal training dates and exclusive API end boundaries. Light/dark desktop and mobile layouts were also inspected in the running preview. The [gallery](screenshots/README.md) uses explicitly synthetic fixture data; the development preview can use the published real snapshots.
