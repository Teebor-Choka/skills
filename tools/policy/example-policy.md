---
# Machine keys (frontmatter). All optional; absent → the basic default. See the policy skill.
mode: single                       # single | team (team opts into parallel splitting)
interaction: batch                 # batch | dialog — grilling rhythm
grounding: auto                    # auto | none | <tool>
gate: plain                        # plain | tests | rubric
toolchain: [codegraph, pytest]     # automated tools grounding/verification may use
practices:                         # injected at the level they belong to
  scope: ATDD
  task: TDD
ramble:                            # per-skill section: overrides the global key for `ramble` only
  interaction: dialog
---

# Development policy

Machine keys live in the frontmatter above; this body is prose and pointers, not parsed. Keep every
process constant here, never baked into a skill.

- **mode** — `single` (one actor) or `team` (opt into parallel, non-overlapping splitting; only then
  are `substrate`/`comms` read).
- **interaction** — how the ramble front door asks: `batch` (whole frontier per round) or `dialog`
  (one question at a time).
- **grounding** — `auto` uses a code-graph / codebase-memory index when present, else plain reads.
- **gate** — how "done" is judged: a plain checklist, executable `tests`, or a `rubric` (judge).
- **practices** — e.g. ATDD at the scope level, TDD at the task level; empty forces none.

Prose pointers (not machine-read): [`glossary.md`](./glossary.md), [`style.md`](./style.md). This file
is optional and layered — a global `~/.agents/policy.md` is overridden per key by this local copy;
its absence resolves to the basic default.
