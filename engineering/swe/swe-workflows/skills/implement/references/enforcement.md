# Enforcement

Reading policy is not enforcing it. A gate you grade yourself is theater. Enforcement is real
only where it is **external to the implementer** — something that cannot be talked into the
shortcut.

## Who enforces (never the author)

- **CI / the project gate** — machine, unfakeable: tests, lint, build.
- **The quality tool's own numbers** — the project method or the skill policy key `quality` names;
  thresholds, verified per finding.
- **The isolated adversarial reviewer** — a separate context (subagent or fresh worktree) that
  did not inherit the author's rationalizations.
- **The external review bot** — a distinct identity (e.g. CodeRabbit) on the change request.
- **Git history** — the failing-test-first commit is an artifact anyone can check.
- **The hook** — at commit / ready / integrate, queries the forge binding for the boundary's
  real state and runs `policy-gate`, blocking only a genuinely unmet boundary; the one
  enforcement a session cannot skip by choosing not to.

## Key → gate → what blocks

| Policy                  | Gate (step)    | Blocks when                                                       |
| ----------------------- | -------------- | ----------------------------------------------------------------- |
| `practices.scope: ATDD` | spec check (2) | acceptance tests absent or not agreed before design               |
| `practices.task: TDD`   | implement (3)  | no functional failing-test commit precedes the implementation     |
| `gate: tests`           | quality (4)    | the project's tests/metrics are not green                         |
| `gate: rubric`          | review (5,7)   | the isolated review or the bot has unresolved actionable findings |
| `gate: plain`           | acceptance     | the item's criteria are not all met (weak — low-risk items only)  |
| `mode: team`            | integrate (8)  | the merge dial's conditions are unmet (CI + review clean)         |

The TDD red is only artifact-checkable, so it is enforced two ways that don't trust the
author: the **committed failing test** must exist in the branch history, and the **isolated
reviewer** must confirm the red failed on behaviour, not compilation. Missing either → the
review gate blocks.

## The `policy-gate` contract

`scripts/policy-gate.sh <repo> gate <spec|tdd|quality|review|integrate> [--target FILE] [--ok]`

- Resolves `practices`/`gate`/`mode` and prints the gate's requirement. Forge-neutral — it does
  not query CI or the review bot.
- `--ok` = the caller asserts the external condition passed (CI green, review clean, artifact
  present). `gate.sh` derives it from the forge binding (`scripts/forge-state.sh`); a human or
  another tool can also set `SWE_GATE_OK=1`.
- Exit: `--ok` → 0. Else `mode: team` → **1 (block)**, `mode: single` → **0 (warn)**.

## Wiring the hook

Wire `policy-gate` at the three boundaries so it holds even when a session skips this skill.
On Claude Code, a `PreToolUse` hook on the integrate/commit action; the equivalent on other
agents. The hook runs `policy-gate <repo> gate <boundary>` and treats a non-zero exit as a
hard stop (`team`) or a logged warning (`single`). The shipped `hooks/gate.sh` adapter maps a block to the exit code its host treats as blocking
(documented in the script header), and `hooks/boundary.py` matches a boundary command only at the head of a command segment. This is the one check outside the agent's
discretion — keep it. (Hook wiring is an adapter, not the portable core.)

## Pre-tool checks

Check these before a tool call runs, in a pre-tool hook where the host has one, not as prose the
agent must remember:

- Worktree paths: after `worktree add` or entering a worktree, an edit under another checkout of
  the same repo is denied with the worktree path to use instead. Re-read the file by its worktree
  path before the first edit.
