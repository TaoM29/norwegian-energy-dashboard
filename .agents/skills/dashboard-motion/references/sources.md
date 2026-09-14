# Motion references

Reviewed 2026-09-14. Read only the source relevant to the interaction being changed.

- [Transitions.dev catalog](https://transitions.dev/) and [agent skill overview](https://transitions.dev/skill.html): useful patterns include tabs, panels, accordions, loading-to-content transitions, and action feedback. Use their examples as references for a small consistent motion vocabulary.
- [beUI agent index](https://beui.dev/llms.txt): locate exact component source and registry dependencies. [Tabs](https://beui.dev/components/motion/tabs) can show selection continuity; [Number Animation](https://beui.dev/components/motion/number) supplies an accessible-number pattern to inspect and adapt. Avoid animated counting if it would imply intermediate measured values.
- [Rare UI](https://www.rareui.com/): optional inspiration only. Verify reduced-motion and screen-reader behavior in a chosen component; do not infer it from unrelated components or a marketing claim.

The Transitions.dev site describes reduced-motion support, but integrated behavior still needs checking. Its [terms](https://transitions.dev/terms.html) distinguish snippet usage from redistributing a competing collection; do not label all snippets MIT. beUI's free repository has an [MIT license](https://github.com/starc007/ui-components/blob/main/LICENSE), while Pro is a separate offering. Recheck the terms attached to the actual item before copying it.

No remote installer, private registry, paid access, or motion runtime is installed by this skill. The project-local guidance is independently authored around these references.
