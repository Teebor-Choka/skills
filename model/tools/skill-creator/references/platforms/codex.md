# Platform: Codex (OpenAI Codex CLI)

Docs: https://learn.chatgpt.com/docs (developers.openai.com/codex redirects there); repo
https://github.com/openai/codex; examples https://github.com/openai/skills. Codex moves fast
and some docs are undated — verify against your installed version.

## Skill install locations

Skills live under `.agents/skills` (NOT `.codex/skills`), scanned in priority order:

- `./.agents/skills/<name>/` (cwd), `../.agents/skills/`, `$REPO_ROOT/.agents/skills/`
- `~/.agents/skills/<name>/` (user), `/etc/codex/skills` (admin), bundled (system)

Same open Agent Skills standard: `SKILL.md` with `name` + `description` front matter and a
Markdown body, plus optional `scripts/`, `references/`, `assets/`, and an optional
`agents/openai.yaml`.

## Frontmatter and Codex extras

Portable `name` + `description` are all that's required; `description` drives implicit
selection (front-load the "use when…" cases). Codex-specific metadata goes in
`agents/openai.yaml` (not the portable frontmatter): display name/icon, a `default_prompt`,
`policy.allow_implicit_invocation = false` (force explicit-only), and MCP tool `dependencies`
the skill auto-wires. Enable/disable a skill in `~/.codex/config.toml`:

```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = false
```

## Instruction files (always-on, complements skills)

`AGENTS.md` gives layered, always-loaded instructions: `~/.codex/AGENTS.md` < repo-root <
subdir (closer overrides farther); `AGENTS.override.md` for temporary local overrides. Use it
for repo conventions, not reusable capabilities — prefer a skill for anything triggered.
`project_doc_max_bytes` (default 32 KiB) caps combined size;
`project_doc_fallback_filenames` adds alternate names.

## Triggering

- **Implicit** — from `description` (metadata capped ~2% of context up front).
- **Explicit** — `$skill-name` in the CLI/IDE (`@skill` in ChatGPT).
- **Custom prompts** — `~/.codex/prompts/*.md` (`/prompts:<name>`), legacy; prefer a skill.
- **Profiles** — deterministic config bundles, selected with `-p <name>`. Current form is a
  per-file `$CODEX_HOME/<name>.config.toml` (older inline `[profiles.<name>]` may still work):
  ```toml
  # ~/.codex/ci.config.toml
  model = "gpt-5.6-sol"
  approval_policy = "never"
  sandbox_mode = "workspace-write"
  ```
- **Hooks** — `[[hooks.PreToolUse]]` (and other lifecycle points) in `config.toml`, running an
  external command with a `matcher` and `timeout`. Admins: `allow_managed_hooks_only = true`.

## Advanced workflows

- **Subagents** — role-specialized subagents with distinct configs/tool access (e.g. one runs
  tests, another reads logs via MCP): Codex's delegation layer.
- **MCP** — Codex is an MCP client: `[mcp_servers.<name>]` in `config.toml` (stdio
  `command`/`args`, or HTTP `url` + `bearer_token_env_var`); `codex mcp add`, `codex mcp list`.
- **Orchestration** — no scripting engine; chain `codex exec` calls in the shell and resume
  sessions.

## Headless / CI: `codex exec`

```bash
codex exec --json -p ci --sandbox workspace-write -o summary.txt "\$<name> for the pending release"
```

Key flags: `--json`, `-o/--output-last-message`, `-p/--profile`, `-C/--cd`,
`-a/--ask-for-approval on-request|never`, `-s/--sandbox read-only|workspace-write|danger-full-access`,
`-m/--model`. Resume: `codex exec resume <SESSION_ID>` / `--last`.

## Minimal adapter set

Portable `SKILL.md` in `~/.agents/skills/<name>/` (or repo `.agents/skills/<name>/`) works as
is. For CI/determinism add a profile and drive it with `codex exec -p <profile> "$<name> …"`.
Add `agents/openai.yaml` only for explicit-only policy or MCP dependency wiring.
