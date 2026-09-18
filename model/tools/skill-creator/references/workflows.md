# Advanced multi-agent workflows across agents

When a skill needs more than one agent — parallel research, a plan-then-build split, an
adversarial reviewer, a fan-out over many files — keep the _intent_ in the portable SKILL.md
("delegate exploration to a read-only subagent, then implement from its findings") and bind it
to each agent's mechanism in an adapter.

| Capability                  | Claude Code                                                   | Codex                                       | OpenCode                                                              |
| --------------------------- | ------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------- |
| Subagents                   | `.claude/agents/<name>.md`; the Agent tool; `@"name (agent)"` | role-specialized subagents (config-defined) | `.opencode/agents/<name>.md` or `agent` key; `@name`; the `task` tool |
| Deterministic orchestration | the Workflow tool (JS: `agent()`, `parallel()`, `pipeline()`) | shell over `codex exec` + session resume    | shell over `opencode run` + `serve --attach`                          |
| Parallel fan-out            | multiple Agent calls / Workflow `parallel`                    | multiple `codex exec` processes             | General subagent; multiple `opencode run`                             |
| Nesting bound               | per-call                                                      | per-config                                  | `subagent_depth` (default 1)                                          |
| External tools              | MCP (`mcp__server__tool`)                                     | MCP client (`[mcp_servers.*]`)              | MCP (`mcp` key)                                                       |

## Subagent definitions

- **Claude Code** — `.claude/agents/<name>.md` with frontmatter (`name`, `description`,
  `tools`, `model`, `permissionMode`, `skills`, `mcpServers`, `isolation: worktree`). Invoke
  in natural language, guarantee with `@"name (agent)"`, or via the Agent tool. A skill can
  even run in a subagent itself via `context: fork` frontmatter (adapter-only key).
- **OpenCode** — `.opencode/agents/<name>.md` (filename = agent name) or the `agent` key in
  `opencode.json`. Fields: `description`, `mode` (`primary|subagent|all`), `model`, `prompt`,
  `temperature`, `steps`, `permission`. Invoke by auto-delegation, `@name`, or the `task`
  tool; `subagent_depth` bounds nesting.
- **Codex** — role-specialized subagents with distinct configs/tool access (e.g. one runs
  tests, another reads logs via MCP). This is Codex's delegation layer; there is no
  Workflow-style scripting engine, so multi-step orchestration is done with `codex exec`.

## Deterministic orchestration (when model-driven delegation isn't enough)

- **Claude Code** has a first-class Workflow tool: a JS script with `agent()`,
  `parallel()`, and `pipeline()` for fan-out/verify/synthesize with real control flow. Use it
  for structured multi-agent passes (e.g. find → adversarially verify → dedupe). This is
  Claude-specific; do not put it in the portable body.
- **Codex and OpenCode** orchestrate through the shell: run the headless command per stage,
  parse JSON output, feed the next stage, and keep state with session resume or a persistent
  server. A skill that needs this ships a `scripts/orchestrate.sh` (or `.py`) and each agent's
  adapter calls it — the portable core just describes the stages.

## Portability guidance

- Describe orchestration as _intent and stages_ in the portable body; never hard-code
  `Task(...)`, `@"x (agent)"`, `skill({...})`, or Workflow JS there — those break on the
  other agents.
- If the workflow is genuinely deterministic (fixed stages, no model judgment between them),
  prefer a bundled script driven by each agent's headless command. It is the most portable and
  testable form, and it runs the same in CI.
- Reserve model-driven subagent delegation for open-ended stages (research, review) where the
  agent should decide how deep to go.

## External tools (MCP) — common ground

All three are MCP clients, so a skill that needs an external tool declares the dependency and
lets each agent wire the server:

- Claude Code: `mcpServers` in `settings.json` or per-subagent; tools appear as
  `mcp__<server>__<tool>`.
- Codex: `[mcp_servers.<name>]` in `config.toml` (stdio `command`/`args` or HTTP `url`);
  `codex mcp add`.
- OpenCode: the `mcp` key in `opencode.json`; `opencode mcp add`.

Name the required MCP tools in the skill's docs and gate them with each agent's permission
model rather than assuming they are always present.
