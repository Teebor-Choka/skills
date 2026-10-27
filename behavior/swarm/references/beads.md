# Binding: beads (`bd`)

Default binding. Source: steveyegge/beads, `README.md` and `docs/CLI_REFERENCE.md` (read
2026-10-27). `bd` was not installed on the authoring host, so none of this is tested. Before the
first run, check each command with `bd <cmd> --help` and `bd schema`, and fix this file if it
differs.

| Verb           | `bd` command                                                                                                                          |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| file           | `bd create "<title>" -d "<body>" --acceptance "<tests>" -l <labels> -p <n> -t <type>`                                                 |
| list           | `bd list -s <state> -l <label> -a <agent> --json`; ready work: `bd ready --json`                                                      |
| show           | `bd show <id> --json --include-comments`                                                                                              |
| claim          | `bd update <id> --claim` (documented as atomic: sets assignee and `in_progress`)                                                      |
| heartbeat      | `bd heartbeat <id>` (alias `hb`; refreshes the lease on an issue you hold `in_progress`)                                              |
| release / reap | `bd reclaim <id>` (returns the issue to the unassigned pool)                                                                          |
| stale scan     | `bd list -s in_progress --json`, then compare heartbeat age. `bd stale -d <days>` counts whole days: too coarse for a 15-minute rule. |
| note           | `bd comments add <id> "<text>"`                                                                                                       |
| transition     | `bd update <id> -s <status>` or `bd update <id> --add-label state:<name>`                                                             |
| link           | `bd dep add <a> <b> -t <type>`; types include `blocks`, `discovered-from`, `caused-by`, `supersedes`                                  |
| close          | `bd close <id> "<reason>"`                                                                                                            |

## Mapping notes

- **States.** Built-in statuses are `open`, `in_progress`, `blocked`, `deferred`, `closed`. Charter
  states beyond these go in labels named `state:<name>`. Keep exactly one `state:` label per item;
  replace it on transition and log the change.
- **Revision.** Put it in the verdict comment: `verdict: approve rev=<sha>`.
- **Lease TTL.** The docs do not state a default TTL for `bd heartbeat`. Do not rely on one. Apply
  the charter's stale timeout yourself by reading heartbeat age.
- **Not documented.** Whether `updated_at` appears in `bd show --json`; the field names of `--json`
  output (run `bd schema`); the exact `--claim` failure output when the item is held.
- **Git sync.** Beads stores state in git-backed storage. If agents run in separate worktrees or
  hosts, confirm that all of them read the same store before the first claim, or two agents claim
  the same item without seeing each other.
