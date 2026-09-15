# Portfolio UI refresh

Implemented 2026-09-15. The interface supports two levels of reading: a visitor can understand the energy overview and follow a question; an analyst can reach detailed controls, source values, exports and methodological limits.

## What changed

- A persistent desktop sidebar groups the six pages into Workspace, Analysis and Project. A slim top bar keeps the current page and theme controls visible; all destinations remain visible on mobile.
- The overview opens with compact metrics and a sortable five-region consumption table. Region details open in a right-hand drawer with energy totals, generation mix and source coverage for the selected dates. Inspecting a region keeps the current overview intact until “View this region” is selected.
- Light, dark and system themes. Preference persists across visits; charts, tooltips and PNG backgrounds follow the active theme. Theme changes update chart styles without recreating the chart instance.
- A plain-language overview introduction, optional short reading guides and three pathways into exploration, forecasting and project methods.
- Diagnostic choices describe the question first. Model parameters sit under “Method settings”; keyboard arrows move between choices.
- The explorer starts with daily summaries; explicit hourly/weekly URL selections still work. Line opacity is under “Display options”. The underlying aggregation rules, source values and exports are unchanged.
- Neutral charcoal and light surfaces, compact pill controls, subtle row dividers and restrained hover/press feedback. Theme changes apply immediately without color transitions. The detail drawer supports Escape, focus return and keyboard opening without motion. Reduced-motion preference removes those transitions. No animation framework or runtime dependency was added.

## References and selection

Reviewed [Beautiful UI](https://www.beautifului.dev/), [beUI’s catalog](https://beui.dev/llms.txt), [Rare UI](https://www.rareui.com/), [Transitions.dev](https://transitions.dev/) and [shadcn/ui](https://ui.shadcn.com/docs/components). Applied the ideas of clear navigation, compact selection controls, optional detail and restrained state feedback. The existing shadcn-style buttons/cards and native disclosures were sufficient; no third-party component source was copied.

The supplied CRM screenshots informed the compact workspace structure, neutral selected rows, small badges and detail drawer. Applied [Emil’s design engineering skill](https://www.skills.sh/emilkowalski/skills/emil-design-eng) and [better-ui](https://www.skills.sh/jakubkrehel/skills/better-ui) for surface hierarchy, interaction feedback and restrained motion. The drawer uses native dialog behavior for focus and dismissal.

## Verification

TypeScript and production builds pass. Seven Chromium journeys cover the existing analytical routes and downloads plus system theme changes, saved preference across navigation/reload, 390px layouts, reading guides, hidden/revealed settings, keyboard method selection reduced-motion mode, region sorting and keyboard drawer dismissal/focus return. Light/dark desktop and mobile layouts were also inspected in the running preview. The [gallery](screenshots/README.md) uses explicitly synthetic fixture data; the development preview can use the published real snapshots.
