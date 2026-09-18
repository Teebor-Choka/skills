---
name: skill-creator
description: >
  Author, port, and harden agent Skills (SKILL.md) that work across Claude Code, Codex,
  and OpenCode from one portable source. Use whenever the user wants to create a new
  skill, turn a repeatable workflow into a skill, fix or improve an existing skill's
  triggering, make a skill run on more than one agent, or wire a skill into programmatic
  triggering (description auto-trigger, slash/custom commands, hooks, CI/headless runs) or
  advanced multi-agent workflows (subagents, parallel fan-out, orchestration, MCP). Trigger
  even when the user just says "make a skill", "package this as a skill", "why isn't my
  skill firing", "add a command or hook for this", or names Codex or OpenCode alongside
  skills. Produces a portable SKILL.md plus per-agent adapters and an evaluation harness.
---

# Skill creator (cross-agent)

Create skills that run unchanged on **Claude Code**, **Codex**, and **OpenCode**, then add
per-agent adapters for programmatic triggering and multi-agent workflows.

The load-bearing fact: all three implement the same open **Agent Skills** standard — a
`SKILL.md` directory (YAML `name` + `description` front matter, Markdown body, optional
`references/`, `scripts/`, `assets/`). Write the capability once as a portable core; add
thin per-agent adapters only where you need deterministic triggering or orchestration.

```
skill-name/
├── SKILL.md          # portable: name + description + instructions (all three read this)
├── references/       # loaded on demand (progressive disclosure)
├── scripts/          # deterministic helpers, runnable without loading into context
└── assets/           # templates/resources used in output
```

## Where a skill is installed per agent

| Agent       | Skill search paths (project / user)                              | Also reads                           |
| ----------- | ---------------------------------------------------------------- | ------------------------------------ |
| Claude Code | `.claude/skills/<name>/` · `~/.claude/skills/<name>/`            | plugin `skills/`                     |
| Codex       | `.agents/skills/<name>/` · `~/.agents/skills/<name>/`            | `/etc/codex/skills`, bundled         |
| OpenCode    | `.opencode/skills/<name>/` · `~/.config/opencode/skills/<name>/` | `.claude/skills/`, `.agents/skills/` |

OpenCode reads `.claude/skills` and `.agents/skills` too, so a single checked-in skill dir
can serve all three. Details and exact precedence: `references/platforms/*.md`.

## Workflow

Follow this loop. It is the same discipline whichever agent you target.

1. **Capture intent.** What should the skill let the agent do, and _when should it
   trigger_? Pull answers from the conversation if the user said "turn this into a skill".
   Nail the trigger contexts — the `description` is the whole triggering mechanism.
2. **Decide portability.** Default to a **portable core** (see `references/authoring.md`):
   plain instructions, no agent-specific tool calls in the body. Add per-agent adapters
   only for triggering/orchestration you actually need. If the skill must dispatch
   subagents or call vendor tools, keep that in an adapter, not the core.
3. **Write `SKILL.md`.** Frontmatter (`name`, `description`) + a lean body. Push detail
   into `references/`; put deterministic, repeated work into `scripts/`. Keep the body
   under ~500 lines. Craft rules and the description in `references/authoring.md`.
4. **Add adapters** for the target agents (only what's needed):
   - Programmatic triggering — auto-trigger by description, slash/custom commands, hooks,
     CI/headless entry points. Matrix + snippets: `references/triggering.md`.
   - Advanced workflows — subagents, parallel fan-out, pipelines, MCP. Patterns per agent:
     `references/workflows.md`.
   - Exact per-agent file formats: `references/platforms/{claude-code,codex,opencode}.md`.
5. **Evaluate.** Build test cases and run the skill with vs without it on each target
   agent, grade against assertions, and compare. Full harness: `references/evaluation.md`.
   Scaffolding: `assets/evals.example.json`, and `scripts/validate_skill.py` for a
   fast frontmatter + portability lint.
6. **Iterate.** Improve from the eval results and re-run. Generalize from feedback rather
   than overfitting to one test. Stop when the user is satisfied or gains stall.

To raise an _existing_ skill set (and its `CLAUDE.md`/`AGENTS.md` and hooks) to standard,
run the approval-gated audit in `references/auditing.md`: rewrite rules as the standard behind
them, turn example-copying creative skills into interfaces, and route always-on context into
reference files. Two craft principles behind it — standards over rules, and interface over
example — are in `references/authoring.md`.

## Portability rules (the core must stay agent-neutral)

These keep one `SKILL.md` working everywhere. Full rationale in `references/authoring.md`.

- **Required frontmatter is only `name` + `description`.** `name`: 1–64 chars,
  `^[a-z0-9][a-z0-9-]*$`, matching the directory. `description`: 1–1024 chars, no angle
  brackets. Optional portable keys: `license`, `compatibility`, `metadata`.
- **Any other frontmatter key is agent-specific** (e.g. Claude's `allowed-tools`,
  `context: fork`, `paths`; Codex's `agents/openai.yaml`). Keep those in adapters, not the
  portable core — unknown keys are ignored by some agents and rejected by strict linters.
- **The body is plain instructions.** Do not hard-code a specific agent's tool calls (the
  Task tool, an @-agent mention, the skill() tool) in the portable body; describe the intent
  ("delegate research to a subagent") and let each adapter wire the mechanism. The exact
  patterns to avoid are in `references/authoring.md`.
- **Reference files by relative path**; assume only a POSIX shell and the languages you
  bundle in `scripts/`. Don't assume a particular model or provider.

## Success criteria

A skill is done when: it triggers on the intended prompts and stays quiet on near-misses
(test both — see the trigger evals in `references/evaluation.md`); the portable core runs on
every target agent; each adapter is the minimum needed; and the eval harness shows it beats
the no-skill baseline on the cases the user cares about.
