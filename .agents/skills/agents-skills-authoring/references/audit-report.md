# Audit-only report

Use this format when the user requests an audit or diagnostic report. Follow any format the user explicitly requests instead.

State the reviewed scope and list the files inspected. Identify exclusions or unreadable files; do not imply complete coverage when files are missing. Evaluate supporting skill instructions when they fall within the requested scope, not only the entrypoint.

For each supported finding:

FLAGGED — [number and name of one of the six checks] — [quoted instruction and file:line]
Why: [the current problem; the original purpose if evidenced, otherwise label it as inferred or unknown]
What to do: [delete, shorten, split into a router, or rewrite; give a concrete proposed change]

For retained instructions, group closely related rules if helpful:

KEEP — [instruction and file:line]
Why: [the enduring project fact, security boundary, team standard, or operational requirement]

Do not manufacture findings to populate every category. Keep uncertain consequential rules provisionally and explain what evidence is missing.

End with one line giving approximate percentages for categories 1–6 and KEEP. Use discrete reviewed instruction units as the denominator and state their count. Assign each unit to one primary category to avoid double-counting; percentages should total roughly 100%. Count provisionally retained rules as KEEP and disclose that choice. If there are no instructions, report N/A rather than invented percentages.
