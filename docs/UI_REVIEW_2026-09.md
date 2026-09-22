# Dashboard design review · September 2026

## Goal

Make the project understandable on a first visit while keeping its scientific evidence inspectable. The intended reading order is: choose a scope, see a result, inspect supporting evidence, then open the method if needed. The audience includes a potential employer evaluating both the interface and the quality of the analysis.

## Findings and changes

| Finding | Change | What remains available |
| --- | --- | --- |
| Two published study pages returned 404 because the deployment snapshot omitted their artifacts. | Package and repin a complete snapshot. Packaging and build checks now reject missing or empty required study files. | Original published archive, unchanged study artifacts and retained replay evidence. |
| Repeated page introductions and uppercase labels delayed the first useful result. | Short headings, one-sentence descriptions, inline contextual help and a compact source footer. | Detailed interpretation and source documentation in Methods and relevant result disclosures. |
| Six equally prominent buttons made Patterns feel like another navigation bar. | One labeled analysis selector with the existing deep-link values. | All six analyses and their area/date state. |
| A missing publication appeared as a large red error with an ineffective Retry button. | A neutral missing-study state links to available observations. Transient failures retain Retry and the server's error message. | Loading, unavailable-area, invalid-result and network failure states remain distinct. |
| Overview repeated the same production insight and long historical case studies. | Remove the duplicate observation panel; add concise links to forecasting, sensitivity and project evidence. Compact headline metrics and remove help controls that repeated visible notes. | Full historical case studies remain in Methods. Daily values and exports remain on Overview. |
| Explore and Regional exposed too many settings and secondary tables at once. | Keep primary filters visible; disclose secondary filters and supporting breakdowns. | Group selection, aggregation, weather settings, snow assumptions, all data tables and exports. |
| Saved-study metrics competed with the main chart. | Put sensitivity and anomaly charts first. Use lighter summary rows and disclose secondary diagnostics and peer-day matching. | Model comparisons, residual checks, support, coverage, downloadable artifacts and candidate selection. |
| Forecast chart controls and all-area evaluation had unclear scope. | Put the selected forecast chart before extended study reports and label benchmark versus chart scope. | Saved benchmarks, reliability and ablation reports, model/cohort controls and local experiments. |
| Methods read as one long tutorial. | Lead with coverage, sources and evidence; disclose guides and detailed protocols. | Forecast model assumptions, retrospective-study caveats, scientific case studies and reproduction instructions. |
| Repeated saturated surfaces and large rounded containers gave every element similar weight. | Use a restrained blue accent, neutral surfaces, smaller corner radii, lighter metric treatments and a simpler sidebar. | Light/dark themes and stable semantic chart colours. |

## Scientific and interaction boundaries

No model was refitted, threshold changed, observation altered or scientific evidence removed for this redesign. Associations remain explicitly non-causal. Screening bands remain distinct from confidence or prediction intervals. Missing values remain gaps. The demand-change study's excessive false-alarm rate and sensitivity to assumptions remain visible beside its finding.

The interface uses the existing React, Radix/shadcn-style controls and native disclosures. No component library, font, animation package or automated fitting process was added. Labels, keyboard focus, URL state, exports and accessible data tables remain part of the interface.

## Design references

The requested skills guided the changes in these ways:

- [Frontend design](https://github.com/anthropics/skills/blob/34040c9c5685/skills/frontend-design/SKILL.md): choose an analytical visual direction and remove generic decorative copy.
- [Apple design](../.agents/skills/apple-design/SKILL.md): typography, restraint, spatial consistency and content hierarchy.
- [Beautiful shadows](../.agents/skills/beautiful-shadows/SKILL.md): restrained neutral elevation; keep existing low-key surface shadows instead of adding effects.
- [Accessibility](https://github.com/addyosmani/web-quality-skills/blob/afa8da942115/skills/accessibility/SKILL.md): labels, keyboard interaction, focus and responsive reading order.
- [Design review](https://github.com/Superfuture/design-review/blob/d4d2609b53fc/design-review/skills/design-review/SKILL.md): prioritize broken states and hierarchy ahead of cosmetic changes. Only the critique rubric was used; no telemetry or external artifact-review service was invoked.
- [Emil design engineering](https://github.com/emilkowalski/skills/blob/85e8e2363b71/skills/emil-design-eng/SKILL.md): readable controls, measured spacing and interaction feedback.
- [shadcn](https://github.com/shadcn-ui/ui/blob/98a1fe67b439/skills/shadcn/SKILL.md): reuse the existing component system and Radix Select.
- [Adapt](https://github.com/pbakaus/impeccable/blob/83c2c735777c/skill/reference/adapt.md): narrow-screen layouts and progressive disclosure.
- [Better interface](../.agents/skills/better-interface/SKILL.md): copy, layout, type, colour and accessibility review together.
- [Interaction design](../.agents/skills/interaction-design/SKILL.md): distinguish loading, missing publication and recoverable request failures without decorative motion.

## Release data

The replacement archive includes all three prepared demand studies, the published energy database, weather and geography, and saved forecast results. Its public download was streamed back and verified against SHA-256 `67bc064823d3a34dae19b78093d3796500440bac6d2d522687c1ae078c198f7d` (97,761,155 bytes). The packaged SQLite database passed `PRAGMA quick_check`.

The previous archive, SHA-256 `727aab8c951fa1543ea8edaca79f854426926bfdc766f43ed4fdb9fa135cf0b8`, remains available for rollback. The updated manifest and code must be released together. Uploading an archive alone does not update the running website. See [release operations](RELEASE.md).

## Verification

- Python suite: **340 passed**. Two existing dependency deprecation warnings remain.
- New snapshot: all three saved artifacts included; SQLite integrity check and remote SHA-256 verification passed.
- New colour pairs reviewed: action/white 6.76:1, light accent/soft surface 5.88:1, dark accent/surface 9.38:1, dark accent/soft surface 7.27:1.

- Production Next.js build and TypeScript checks: passed.
- Browser suite: **51 checks passing** across the full run and focused rerun of six corrected tests. Coverage includes filter staging, URL/history, keyboard controls, exports, responsive tables, both themes, retained study limitations, and all three missing-study/retry flows.
- Visual review in the Codex Chromium preview: desktop Overview in both themes; Explore, Regional, Forecasts and Methods; observed anomaly and sensitivity studies; a 390 px demand-change view in both themes. The automated suite also checks 320 px layouts. Confirmed charts render after expanding the sensitivity diagnostics.
- `git diff --check`: passed.
- `python scripts/check_secrets.py --history`: passed (MongoDB credential-pattern scan).

Visual review is scoped to these flows; it is not a complete assistive-technology audit. Physical iOS/Android devices, Safari/Firefox and screen readers were not tested. These checks were completed before release. The complete public snapshot is pinned in the manifest; pushing the changes to main triggers the frontend and API deployments described in RELEASE.md.
