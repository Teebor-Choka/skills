# Installing swe-workflows per harness

The `implement` skill (the loop) is portable — every harness reads it from a skills dir. The
**policy-gate hook** (the enforcement) is a thin native overlay per harness, all calling the
same `hooks/gate.sh`. Install the skill once, then the overlay for each harness you use.

The hook checks the boundary's real forge state (CI + review via the binding) and, under
`.agents/policy` `mode: team`, **hard-blocks** only a commit/ready/integrate that is genuinely
unmet — a green, reviewed merge passes with no override. Under `mode: single` it **warns**.

## Requirement: the `harness` plugin (`harness:policy`)

swe-workflows reads `.agents/policy` through the loader of the `policy` skill, which the `harness`
plugin of the same marketplace ships (`ai/harness`, skill `harness:policy`). Install it first; without
it `policy-gate.sh` fails with `policy_loader.py not found` and the SessionStart context hook stays
silent.

`skills/implement/scripts/find-loader.sh` probes, in order: `$AGENTS_POLICY_LOADER` (a file path; a
wrong path fails, no fallback), `~/.config/agents/skills/policy`, `~/.claude/skills/policy`,
`~/.agents/skills/policy`, `ai/harness/skills/policy` in the same repo checkout (found from the
script's own path), `~/.claude/plugins/cache/<marketplace>/harness/<version>/skills/policy` (newest
version), `~/.claude/plugins/marketplaces/<marketplace>/ai/harness/skills/policy`, and
`~/.config/agents/skills-src/public/ai/harness/skills/policy`. The plugin-cache layout is taken from
installed Claude Code plugins. For Codex and OpenCode the plugin layout is unverified: link or copy the
skill into `~/.agents/skills/policy`, or set `AGENTS_POLICY_LOADER`.

The Claude Code marketplace entry declares the dependency (`dependencies` in
`.claude-plugin/marketplace.json`). The Codex marketplace format has no verified dependency field, so
there it is this note only.

## Claude Code — plugin + hook

```
/plugin marketplace add Teebor-Choka/skills
/plugin install swe-workflows@kauki-skills
```

Bundles the skill (runs as `swe-workflows:implement`) and `hooks/hooks.json`: the blocking
`PreToolUse` gate, and a `SessionStart` hook (`policy-context.sh`) that injects the resolved
`.agents/policy` as session context. Active on install.

`hooks/hooks.json` is generated from `hooks/manifest.json`: after editing the manifest run `scripts/render-hooks.sh engineering/swe/swe-workflows` from the repo root.

## oh-my-pi — skill + hook overlay

- Skill: oh-my-pi reads the Claude-compatible marketplace and the `.agents/skills` dir, so the
  skill installs with the plugin or via the skills dir.
- Hook: link the overlay into oh-my-pi's pre-hook dir:
  ```
  ln -s <this>/hooks/omp/policy-gate.mjs ~/.omp/agent/hooks/pre/swe-workflows.mjs
  ```
  (or project `.omp/hooks/pre/`). Verify the veto shape against your installed `omp` build —
  the block path moves fast; the warn path is stable.

## Codex — plugin + hook

```
codex plugin marketplace add Teebor-Choka/skills   # reads .agents/plugins/marketplace.json
codex plugin install swe-workflows
```

The plugin's `plugin.json` declares the hook under `extensions.com.openai.hooks` (→ `gate.sh`).
The skill also reaches Codex via `~/.agents/skills/implement`. If you prefer a user-level hook,
add it to `config.toml`:

```toml
[[hooks.PreToolUse]]
matcher = "shell"
command = "<this>/hooks/gate.sh"
timeout = 10
```

## OpenCode — skill + guardrail module

- Skill: OpenCode reads `.claude/skills` and `.agents/skills`, so the skill is available there.
- Guardrail: drop or link the module into the plugins dir:
  ```
  ln -s <this>/hooks/opencode/guard.mjs .opencode/plugins/swe-workflows.mjs
  ```
  It throws in `tool.execute.before` to block. (MCP tool calls historically didn't fire plugin
  hooks — verify.)

## Shared

All four overlays call `hooks/gate.sh`, which resolves `.agents/policy` via the loader of `harness:policy` and exits non-zero to block (team) or zero to warn (single). Change the discipline by
editing policy, never the overlays.

## skill-gate: plugin-contributed rules

`hooks/skill-gate` denies the first edit of a file type until the skill that owns it is loaded.
Its rules are `hooks/skill-gate.rules.json` (`[{"pattern": "<path regex>", "skill": "<plugin>:<name>"}]`);
this plugin ships rows for its own skills only. A plugin that wants a gate ships `skill-gate`,
`skill_loaded.py` and its own rules file, so plugins install independently. `skill_loaded.py` is
the one transcript scan, also used by the `git` plugin's `git-guard`; keep the copies identical (a
test in `git` fails on drift). The hook is wired for Claude Code only; the Codex `plugin.json` and the
oh-my-pi and OpenCode overlays do not carry it.

## Verify the install

Two checks: a portable contract check that needs no agent and no forge, and a one-time live
check per harness.

**Contract check (portable).** The overlays and the gate are covered by tests that need only a
POSIX shell, `bats`, and `node`. From the plugin dir:

    bats tests/              # gate.sh + the forge binding, across every boundary, mode, state
    node tests/overlays.mjs  # each overlay turns gate.sh's exit code into its harness veto

OpenCode throws in `tool.execute.before`; oh-my-pi returns `{ block: true }`. Neither command
needs Nix or a specific forge. This repo additionally wires both into `nix flake check` (the
`swe-gate` and `swe-overlays` checks) for its own CI; that is a convenience, not a requirement.

**Live check (per harness, one-time).** No offline test can tell whether the installed harness's
current build loads the overlay and honors its veto on a real tool call, and the veto API drifts
(see the oh-my-pi and OpenCode caveats above). Confirm it once after install: in a scratch repo
with `mode: team` in `.agents/policy`, drive an **integrate** boundary that is not yet passing
review and watch the hook block it. "Integrate" is whatever your forge binding
(`references/bindings.md`) maps "merge the change-request" to; under the default GitHub binding
that is `gh pr merge <N>`, which the examples below use:

| Harness     | What fires                      | Expected                                          |
| ----------- | ------------------------------- | ------------------------------------------------- |
| Claude Code | PreToolUse on the integrate cmd | blocks; stderr carries `policy-gate: BLOCK`       |
| Codex       | `com.openai` PreToolUse (shell) | the hook blocks the call                          |
| oh-my-pi    | the `tool_call` pre-handler     | vetoes (`block: true`); else check the veto shape |
| OpenCode    | `tool.execute.before`           | throws and aborts the call                        |

Discovery of the skill is confirmed however the host lists it (`claude plugin list`, `opencode
skill`, and so on). A `commit` with no red-first test, or marking a change-request ready on red
CI, exercises the other two gates the same way.
