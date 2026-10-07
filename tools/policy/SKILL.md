---
name: policy
description: The shared .agents/policy format and loader. A skill reads its configuration from here instead of hardcoding a process constant; the policy is optional, layered (global + per-repo override), open (any key), and resolves to a reasonable basic default when absent. Reference for skill authors.
disable-model-invocation: true
metadata:
  version: "1.0.0"
---

Skills read process configuration — how to interact, how to ground, what practices apply — from a
repo's **development policy** rather than baking a constant into the skill. This is that format and its
loader. It is **optional**: absent any policy, everything resolves to a reasonable, almost-basic
default.

## The file

`.agents/policy.md` — frontmatter carries the machine keys; the body is prose and pointers (to
`glossary.md`, `style.md`, …) that the loader does not read. Example: [`example-policy.md`](example-policy.md).

- **Open schema.** Any key is allowed. The loader does not police a fixed set, so a new skill can read
  a new key with no change to the loader. "Malformed" means a _structural_ error (no frontmatter, a bad
  list, an indented line with no parent) — never an unknown key.
- **Per-skill sections.** A frontmatter key whose value is a nested map is a section; a section named
  after a skill overrides the global key for that skill only.

## Resolution

Layered, per key: **baseline < global < local**, local wins.

- baseline — the built-in basic default (below).
- global — `~/.agents/policy.md` (or `$AGENTS_POLICY_GLOBAL`).
- local — `<repo>/.agents/policy.md`.

A skill reading key `K` (optionally for a target file) resolves, **most specific first**: a per-file
`files:` glob matching the target → a per-skill `<skill>` section → the global `K` → baseline[`K`] →
the skill's own fallback. The baseline < global < local layering is applied first per key; per-file and
per-skill selection then happen on the merged result. Nothing requires the files to exist; their
absence is the baseline. A malformed policy errors loudly (it never silently falls back).

## Per-file overrides

Scope a setting to the files it applies to — not a separate policy file per directory. A `files:` map
keys a path glob to an override map; a skill acting on a file gets the **most specific** matching glob
(more path segments, then more literal characters, wins):

```
files:
  "**/*.rs":
    gate: tests
  "docs/**":
    interaction: dialog
```

The skill passes the file as `target`: `get(p, "gate", target="src/lib.rs", default="plain")` → `tests`.
Omit `target` for a repo-wide read.

## The basic default (no policy present)

Minimal, least-surprising, single-actor — the fleet/parallel path is opt-in via `mode: team`, not the
default:

| key           | basic default | meaning                                                                               |
| ------------- | ------------- | ------------------------------------------------------------------------------------- |
| `mode`        | `single`      | one actor carries the work; `team` opts into parallel splitting                       |
| `interaction` | `batch`       | grilling rhythm: `batch` (whole frontier per round) or `dialog` (one at a time)       |
| `grounding`   | `auto`        | use an index/tool if present (codegraph/codebase-memory), else plain reads; or `none` |
| `gate`        | `plain`       | acceptance style: `plain` checklist, `tests`, or `rubric`                             |
| `practices`   | `{}`          | e.g. `{scope: ATDD, task: TDD}`; empty = none forced                                  |

These are not exhaustive — a skill may read any other key and supply its own default. Keys for the
opt-in parallel path (`substrate`, `comms`) are read only when `mode: team`.

## How a skill reads config

Python (the loader is stdlib-only):

```python
from policy_loader import resolve, get
p = resolve(repo_path)                               # baseline < global < local
style = get(p, "interaction", skill="ramble", default="batch")
gate  = get(p, "gate", target="src/lib.rs", default="plain")   # per-file rule, if any
```

Or from the shell:

```
policy_loader.py <repo> --get interaction --skill ramble
policy_loader.py <repo> --get gate --target src/lib.rs   # honor per-file rules
policy_loader.py <repo> --json            # the whole resolved object
policy_loader.py --selfcheck              # acceptance checks
```

Always pass the skill's own `default` to `get()` for a key the baseline doesn't define — that is the
last fallback, so the skill still behaves sensibly with no policy at all.

## Extending

To add configuration, just read a new key with its own default — no change here. Document the key in
your skill so a reader knows it exists; add it to the basic-default table above only if it is broadly
useful. The config lives in data; the loader stays small.
