---
# Machine keys (frontmatter). All optional; absent → the basic default. See the policy skill.
mode: single # single | team (team opts into parallel splitting)
interaction: batch # batch | dialog — grilling rhythm
grounding: auto # auto | none | <tool>
gate: plain # plain | tests | rubric
toolchain: [code-index, pytest] # automated tools grounding/verification may use
practices: # injected at the level they belong to
  scope: ATDD
  task: TDD
work-package: issues # where work items / packages are filed: issues | github | gitlab | jira | beads | none (a binding resolves the verbs)
work: # grouped work settings; read dotted, e.g. work.isolation
  isolation: worktree # worktree | branch | none — workspace per parallel writer
ramble: # per-skill section: overrides the global key for `ramble` only
  interaction: dialog
files: # per-file overrides: most specific matching glob wins
  "**/*.rs":
    gate: tests
  "docs/**":
    interaction: dialog
---

# Development policy

Machine keys live in the frontmatter above; this body is prose and pointers, not parsed. Keep every
process constant here, never baked into a skill.

- **mode** — `single` (one actor) or `team` (opt into parallel, non-overlapping splitting; only then
  are `substrate`/`comms` read).
- **interaction** — how the ramble front door asks: `batch` (whole frontier per round) or `dialog`
  (one question at a time).
- **grounding** — `auto` uses a code indexing MCP when present, else plain reads.
- **gate** — how "done" is judged: a plain checklist, executable `tests`, or a `rubric` (judge).
- **practices** — e.g. ATDD at the scope level, TDD at the task level; empty forces none.
- **work-package** — where work items and architect packages are filed; a binding maps the abstract
  verbs (file item, checks, integrate) to the named tool. `issues` (alias `github issues`) is the
  default spelling; `github` still works. `work.tracker` is the deprecated fallback, read only when
  `work-package` is unset; if both are set and differ, `work-package` wins. Unset and
  inside a GitHub repo with `gh`, the suite defaults to `github`, else `none` (no tracker).
- **work.isolation** — the workspace each parallel writer gets: `worktree`, `branch` or `none`
  (read-only roles need none). Read dotted (`work.isolation`); unset, parallel writers default to
  `worktree`. A run's charter may override it.
- **files** — per-file overrides keyed by path glob (not a policy file per directory). A skill acting
  on a file gets the most specific matching glob; here Rust files gate on tests and docs are drafted in
  dialog.

Prose pointers (not machine-read): [`glossary.md`](./glossary.md), [`style.md`](./style.md). This file
is optional and layered — a global `~/.config/agents/policy.md` is overridden per key by this local copy;
its absence resolves to the basic default.
