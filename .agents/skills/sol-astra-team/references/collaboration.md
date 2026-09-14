# Collaboration tools and assignment contracts

Use the live tool schema if it differs from these examples. The role matrix is in SKILL.md; this reference supplies mechanics only.

## Context and model selection

With the currently exposed `collaboration.spawn_agent`, `fork_turns: "all"` (or omission) inherits the parent's model and reasoning and cannot be combined with overrides. Use `fork_turns: "none"` for a focused assignment with explicit model/effort, or a positive integer string for limited recent history with overrides. Do not pass a numeric JSON value for `fork_turns`.

Full history is useful when earlier decisions matter and inherited settings fit the role. A fresh assignment must carry the user's goal, essential prior decisions, applicable restrictions, allowed paths, and the specific output needed. Tool permissions still apply regardless of context inheritance.

Call collaboration tools directly through their exposed tool interface; they are not functions.exec `tools.*` methods. Examples below are tool argument objects, not scripts to execute or prompts to copy without filling in the assignment.

Scout example:

```json
{
  "task_name": "forecast_scout",
  "model": "gpt-5.6-sol",
  "reasoning_effort": "low",
  "fork_turns": "none",
  "message": "In /Users/taom/Projects/norwegian-energy-dashboard, locate forecast functions and their existing tests. Read-only; no commands that write files, no credential reads, no network, no Git mutations. Read applicable AGENTS.md guidance. Return file and symbol references, the existing test command, and gaps relevant to forecast extraction. Complete this assignment directly. Do not spawn other agents; your parent's delegation instructions apply only to your parent."
}
```

Advisor example:

```json
{
  "task_name": "astra_advisor",
  "model": "gpt-6-astra",
  "reasoning_effort": "high",
  "fork_turns": "none",
  "message": "Advise on a forecast evaluation design in /Users/taom/Projects/norwegian-energy-dashboard. Read-only; no edits, credential reads, network, Git mutations, or additional agents. Follow applicable AGENTS.md requirements. Consult the forecasting section of docs/IMPLEMENTATION_PLAN.md and assess whether realized weather can support an operational backtest. Return a recommendation, assumptions, risks, and a focused validation check with source-file references. Your advice does not authorize implementation or external actions."
}
```

For a worker, add the exact owned files or narrow directory, acceptance conditions, and relevant validation. Specify paths to avoid, collaborators and interfaces, and existing changes to preserve. Give the same leaf boundary as the scout unless a smart worker has an explicit coordination assignment. Delegate relevant instruction discovery; do not require every project document.

## Capacity and messaging

- `list_agents`: inspect the current roster when scheduling or diagnosing capacity. Include agents outside a nested coordinator's subtree when accounting for the shared limit. A full roster means reuse, wait, or do local work; it is not permission to exceed capacity.
- `send_message`: pass evidence or steering to an existing agent; it does not start a new turn for an idle agent. Use returned IDs or canonical task paths for cross-team messages.
- `followup_task`: assign related follow-up work and wake an idle agent. For a live agent, update the existing assignment instead of creating duplicate work.
- `interrupt_agent`: stop obsolete or conflicting work, then reconcile any partial edits before reassigning ownership. Interruption does not delete files or guarantee release of an agent slot.
- `wait_agent`: wait for mailbox/status updates only when no independent work remains. Use bounded waits compatible with user updates (up to 60 seconds here), and inspect the delivered messages. A timeout is not completion. Avoid repeated unchanged status polling.

Before creating a dependent worker, obtain the scout's or advisor's required finding. For independent questions, schedule them together within capacity. Report evidence and uncertainty rather than forwarding raw logs.

The pattern is adapted from the user's supplied article excerpt. [Official subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents) describes delegation and model configuration generally; exact `collaboration` argument names above were checked against this session's tools. Recheck the exposed schema when running in a different client rather than assuming the public configuration-file examples describe this interface.
