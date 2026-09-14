---
name: sol-astra-team
description: Coordinate Sol scouts and workers with Astra advice for complex project work. Use for multi-agent implementation, parallel investigation, or an explicit Astra consultation.
---

# Sol team with Astra advisor

Use a small team for work that benefits from independent assignments. Sol Medium is the intended coordinator. The skill does not change the current model: retain the user's selected coordinator. Identify requested model settings from explicit configuration or dispatch metadata, not generic system identity or self-description. Distinguish requested settings from verified runtime settings when the host does not confirm the actual backend; disclose a confirmed mismatch.

## Assign the right depth

| Role | Model | Reasoning | Responsibility |
| --- | --- | --- | --- |
| Coordinator | `gpt-5.6-sol` | `medium` | User conversation, assignments, decisions, integration |
| Scout | `gpt-5.6-sol` | `low` | Narrow read-only discovery: files, paths, contracts, relevant tests |
| Worker | `gpt-5.6-sol` | `medium` | Scoped implementation and relevant checks |
| Smart worker | `gpt-5.6-sol` | `high` | Difficult implementation or resolving substantial ambiguity |
| Advisor | `gpt-6-astra` | `high` | Read-only advice on a specific difficult decision or failure |

These are defaults authorized by this workflow, subject to the user's model and budget choices and the live tool schema. The article's Light maps to `low` in this tool interface. Use higher effort only when the question warrants it; Ultra is not required. Do not switch to Terra or another family without a user preference or a disclosed reason consistent with the request.

## Coordinate useful work

For a substantive request with independent parts, delegate bounded assignments while doing useful coordinator work. Use parallel scouts for different questions and workers for separate file ownership. Handle a trivial edit directly; do not create agents merely to fill slots. An explicit advisor request warrants consulting Astra on the requested question, while continuing any independent work.

Keep a compact roster of agent IDs, assignments, write ownership, dependencies, and status. Observe the runtime's actual capacity, counting the coordinator, advisors, and descendants. The current environment has four concurrent slots in total; this is a capacity limit, not a team-size target. Do not change concurrency configuration to run this skill.

Use `collaboration` tools for subagents, not user-owned task creation. For exact calls, context handling, and assignment examples, read [the tool reference](references/collaboration.md) when preparing delegation. Reuse agents for related follow-up work. Do not re-investigate an assigned question unless its evidence is incomplete or contradictory.

Give agents clear ownership and names of relevant teammates. They may send dependency findings directly to one another and notify the coordinator of changes affecting scope, interfaces, or ownership. Agents share files: serialize writes to overlapping paths and shared Git state. The coordinator owns integration; delegates do not switch branches, commit, reset, or push.

## Consult Astra deliberately

Ask Astra when an architectural tradeoff, analytical validity question, conflicting evidence, or difficult failure could materially change the solution. Send one focused decision, the evidence already gathered, constraints, candidate approaches if any, and the desired output. Ask for a recommendation, rationale, assumptions, risks, and the smallest useful next check.

Astra advises without editing files, spawning agents, or approving actions. The coordinator evaluates the advice against project evidence and owns the decision. Consult again when new evidence changes the problem; avoid repeated consultations for reassurance. Continue unrelated work while waiting, but do not finalize a decision that depends on a pending consultation.

## Boundaries and completion

Every assignment includes the absolute project root, permitted writes or read-only status, relevant project requirements, authorization limits, and a concrete deliverable. Fresh-context agents need these explicitly. Preserve user restrictions, required checks, and credential handling. Leaf agents work directly without further delegation. A smart worker may coordinate helpers only when explicitly assigned that role with a defined slot budget and ownership boundaries.

Stay responsive to the user with concise progress updates. Forward steering to affected agents and stop obsolete assignments. Keep approvals with the user when actually required; an advisor or worker cannot grant new authority. Continue already authorized work without inventing approval checkpoints.

Before finishing, collect all results required for the deliverable, resolve conflicting findings, inspect changed artifacts, and run relevant integration checks without duplicating successful checks unnecessarily. Report what was delivered, validation, and unresolved limitations. If tools, slots, or a requested model are unavailable, report the limitation and continue suitable work locally; do not silently substitute a model or claim consultation occurred.
