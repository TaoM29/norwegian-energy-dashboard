# Component sources and project fit

Selection recorded 2026-09-14. These are starting points, not installed frontend dependencies. Recheck exact versions, source, and license when adopting code.

| Source | Role in this project | Good candidates / limits |
| --- | --- | --- |
| [shadcn/ui catalog](https://ui.shadcn.com/docs/components) | Preferred foundation | Sidebar, Tabs, Select/Combobox, Calendar/Date Picker, Sheet, Table, Skeleton, Alert, Tooltip. Compose only what the feature needs. |
| [beUI catalog](https://beui.dev/llms.txt) | Optional interaction refinement | Tabs, table behavior, range controls, or a carefully adapted number transition. Check React/Tailwind/Motion dependencies before mixing with the foundation. |
| [Transitions.dev](https://transitions.dev/) | Motion reference | Use the separate dashboard-motion skill when implementing transitions. |
| [Beautiful UI](https://www.beautifului.dev/) | Layout inspiration | Insight cards, filter tables, and information density. Much of the catalog serves AI/chat workflows, which are outside the planned dashboard. |
| [Rare UI](https://www.rareui.com/) | Low-priority accent source | Consider only a demonstrated need; playful orbs, gooey navigation, and theatrical effects do not advance analytical reading. |

## shadcn integration

Use [Next.js installation guidance](https://ui.shadcn.com/docs/installation/next) for an authorized scaffold and [component documentation](https://ui.shadcn.com/docs/components) for chosen controls. shadcn supplies editable component source. Select the project's primitive base and theme consistently; inspect installed configuration rather than initializing it again.

Typical mapping: NO1–NO5 selection to an accessible option group or Select; dates to a suitable date-range control; methods to a Sheet or collapsible section; coverage/freshness to labeled status text; regional comparisons to a sortable table. Do not assume a motion slider supplies date validation, localization, or keyboard behavior out of the box.

The [upstream shadcn skill](https://ui.shadcn.com/docs/skills) is available, but this project uses focused local guidance. Its automatic command-injection syntax is client-specific, and its blanket registry questions are unnecessary here: shadcn is already the selected default. Consult upstream component documentation without copying those workflow assumptions.

beUI offers a free source registry and separate Pro offerings. Use [its agent index](https://beui.dev/llms.txt) to find the exact item and dependencies. A website's accessibility claim is a lead for verification, not proof of the integrated component's behavior. Preserve required license notices for copied code and review item-specific terms; do not assume every source shares one license.
