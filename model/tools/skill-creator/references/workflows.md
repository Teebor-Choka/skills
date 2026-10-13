# Advanced multi-agent workflows across agents

When a skill needs more than one agent — parallel research, a plan-then-build split, an
adversarial reviewer, a fan-out over many files — keep the _intent_ in the portable SKILL.md
("delegate exploration to a read-only subagent, then implement from its findings") and bind it
to each agent's mechanism in an adapter.

| Capability                  | Claude Code                                                   | Codex                                       | OpenCode                                                              | oh-my-pi                                                            |
| --------------------------- | ------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Subagents                   | `.claude/agents/<name>.md`; the Agent tool; `@"name (agent)"` | role-specialized subagents (config-defined) | `.opencode/agents/<name>.md` or `agent` key; `@name`; the `task` tool | `.omp/agents/<name>.md`; the `task` tool; Agent Hub (`Alt+A`)       |
| Deterministic orchestration | the Workflow tool (JS: `agent()`, `parallel()`, `pipeline()`) | shell over `codex exec` + session resume    | shell over `opencode run` + `serve --attach`                          | shell over `omp -p` + `--resume`; `eval` kernel `agent()`/`workpool()` |
| Parallel fan-out            | multiple Agent calls / Workflow `parallel`                    | multiple `codex exec` processes             | General subagent; multiple `opencode run`                             | `task` fan-out into isolated worktrees; `wait` joins                |
| Nesting bound               | per-call                                                      | per-config                                  | `subagent_depth` (default 1)                                          | `task.maxRecursionDepth` (default 2)                               |
| External tools              | MCP (`mcp__server__tool`)                                     | MCP client (`[mcp_servers.*]`)              | MCP (`mcp` key)                                                       | MCP (`.omp/mcp.json`; imports other agents' MCP configs)           |

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
- **oh-my-pi** — `.omp/agents/<name>.md` (or `~/.omp/agent/agents/`) with frontmatter `name`,
  `description`, body = `systemPrompt`, plus `tools`, `spawns`, `model`, `output` (a JSON result
  schema), `blocking`, `autoloadSkills`. Invoked via the `task` tool, which fans out into
  isolated worktrees with peer messaging; watch them in the Agent Hub (`Alt+A`) and join with
  `wait`. It does NOT read `.claude/agents` or `.codex/agents` (different frontmatter contract),
  so an omp subagent is a separate adapter file. Bundled agents: `scout`, `reviewer`,
  `security-reviewer`, `task`, `sonic`.

## Deterministic orchestration (when model-driven delegation isn't enough)

- **Claude Code** has a first-class Workflow tool: a JS script with `agent()`,
  `parallel()`, and `pipeline()` for fan-out/verify/synthesize with real control flow. Use it
  for structured multi-agent passes (e.g. find → adversarially verify → dedupe). This is
  Claude-specific; do not put it in the portable body.
- **Codex, OpenCode, and oh-my-pi** orchestrate through the shell: run the headless command per
  stage (`codex exec`, `opencode run`, `omp -p`), parse JSON output (`--mode json` on omp), feed
  the next stage, and keep state with session resume or a persistent server. oh-my-pi also hosts
  an in-tool `eval` kernel (`agent()`, `workpool()`, `judge()`, `wait()`) for orchestration
  inside a single session. A skill that needs cross-agent orchestration ships a
  `scripts/orchestrate.sh` (or `.py`) and each agent's adapter calls it — the portable core just
  describes the stages.

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

All four are MCP clients, so a skill that needs an external tool declares the dependency and
lets each agent wire the server:

- Claude Code: `mcpServers` in `settings.json` or per-subagent; tools appear as
  `mcp__<server>__<tool>`.
- Codex: `[mcp_servers.<name>]` in `config.toml` (stdio `command`/`args` or HTTP `url`);
  `codex mcp add`.
- OpenCode: the `mcp` key in `opencode.json`; `opencode mcp add`.
- oh-my-pi: `mcpServers` in `.omp/mcp.json` (or `~/.omp/agent/mcp.json`); `/mcp add`. It also
  imports the Claude/Codex/OpenCode MCP configs, so a server declared for another agent is
  usually picked up here.

Name the required MCP tools in the skill's docs and gate them with each agent's permission
model rather than assuming they are always present.
