# Read-only roles and the verify pass

## Read-only by allowlist

Reviewers, validators and advisors judge work. They do not change it.

1. Give them read tools only: read, search, list, and read-only version-control or tracker
   commands. No edit, write, or shell with side effects.
2. State it in the brief: "report only, do not modify any file".
3. Enforce it by tool allowlist or sandbox, not by the instruction alone. Per-host bindings are
   in `agent-extension-author` (platform notes) and `code-quality/references/cross-agent.md`.
4. A patch in a reviewer's output is a suggested fix inside a finding. Never apply it blind.
5. Read-only on the work does not mean read-only on the board: they write findings, verdicts and
   notes to items.

## Verify before acting

A finding is a claim until a second, independent reader confirms it.

1. A validator, or a skeptic subagent in a fresh context, reproduces or traces the scenario from
   the return's evidence.
2. It checks the finding is not a duplicate and not an accepted tradeoff
   (`tradeoffs-template.md`).
3. It checks the acceptance test can fail on the current revision.
4. Only a confirmed finding reaches a worker. A `blocker` is verified by reading the cited code
   before anyone acts.
5. The original reporter confirms the fix at the pinned revision. Two gates (validate, confirm)
   are enough. A third coordinator check rarely catches what these two miss.

Where the check is numeric (complexity, coverage), run the tool, not a reviewer's guess
(`code-quality`).
