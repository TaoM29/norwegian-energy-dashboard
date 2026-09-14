---
name: dashboard-motion
description: Add or review transitions and animated feedback in the energy dashboard. Use for tabs, panels, loading transitions, or changing values when motion helps explain state.
---

# Restrained dashboard motion

Use motion to explain a state change, maintain orientation, or acknowledge an action. Keep analytical values readable and controls responsive. Static layouts and unrelated frontend edits do not need this skill.

## Choose a small effect

Use [the motion source guide](references/sources.md) when finding a recipe. Prefer Transitions.dev for focused examples and selected beUI components when their behavior earns the added dependency. Inspect existing CSS and motion libraries first; simple opacity/transform transitions rarely require another runtime. Preserve a consistent duration/easing vocabulary rather than collecting incompatible effects.

Suitable uses include an active tab indicator, a filter panel entering, a loading state resolving, or an export confirmation. Avoid ambient animation, parallax, dramatic blur, 3D tilt, bouncing metrics, and delayed chart reveals that distract from reading or make the application feel slower. Do not animate every update just because a recipe exists.

## Preserve state and access

Respect prefers-reduced-motion with an immediate or restrained alternative. Never make movement or color the only state signal. Keep focus visible and logical, preserve semantic controls, and support keyboard and touch operation. Ensure panel transitions do not trap focus or leave hidden controls focusable.

For numbers, display the actual final value as accessible text without announcing every animation frame. Avoid intermediate counter values that look like measurements, and do not animate chart paths in ways that suggest unobserved data. Preserve units, sign, precision, timestamps, and uncertainty. Refreshing data must not reset chart zoom or move the reader's focus.

Keep the interface interactive during transitions. Favor bounded transform/opacity effects, avoid unnecessary layout work, and cancel or replace obsolete animations when users change filters quickly. Do not delay real data until an animation completes. Retain honest loading, empty, stale, and failure states.

## Integrate and verify

Inspect the selected recipe's full source, dependencies, license, and client/server requirements before adapting it to project tokens. Public examples do not authorize purchases or private-registry access. Retain notices; store provenance near substantial copied components without copying an entire recipe collection.

For implemented motion, check normal and reduced-motion settings, keyboard focus, rapid repeated actions, and narrow screens in a running preview. Measure added cost when a new dependency or expensive effect could affect the plan's latency goals. Report any preview limitation and relevant checks; do not claim animation quality from code alone.
