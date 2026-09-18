# Authoring a portable SKILL.md

The `SKILL.md` is the one artifact all three agents read. Get it right and the skill runs
everywhere; the adapters only add triggering and orchestration on top.

## Frontmatter

```yaml
---
name: my-skill # 1–64 chars, ^[a-z0-9][a-z0-9-]*$, must equal the directory name
description: > # 1–1024 chars, no angle brackets; the entire triggering signal
  What the skill does AND exactly when to use it (and when not to).
license: MIT # optional, portable
compatibility: any # optional, portable free-text
metadata: # optional, portable map for external tooling
  version: "1.0.0"
---
```

Only `name` and `description` are required and portable. Every other key is agent-specific
(see the platform files) and belongs in an adapter, not here — strict validators reject
unknown keys and some agents ignore them silently, so a "portable" skill that leans on them
is not portable.

## The description is the product

Skills load by progressive disclosure: only `name` + `description` sit in context; the body
loads when the agent decides the skill is relevant. That decision is made **entirely from the
description**, so it must carry both halves:

- **What it does** — the capability, concretely.
- **When to use it** — the triggering contexts, in the user's words, including phrasings that
  do not name the skill or its file types.

Agents tend to _under_-trigger skills. Counter it by being explicit and slightly pushy about
triggers, and by listing near-miss phrasings you _do_ want to catch. Example shape:

> Convert and clean spreadsheet data. Use whenever the user wants to open, fix, reshape, or
> compute over an .xlsx/.csv — even casually ("the sheet in my downloads", "add a margin
> column"). Do not use for Word docs or a database pipeline.

Also state what should **not** trigger it — the near-misses that share keywords but need a
different tool. This is what keeps the skill from firing on adjacent work.

Constraints that keep it portable: keep it under 1024 characters and use no angle brackets
(`<`/`>`) — both are hard limits in common validators.

## Progressive disclosure and structure

Three loading levels: metadata (always in context), the `SKILL.md` body (loaded on trigger),
and bundled resources (loaded or executed on demand). Use them:

- Keep the body lean (aim under ~500 lines). It should orchestrate: state the workflow, the
  contract, and where to look next.
- Push exhaustive material (long rules, tables, per-variant detail) into `references/*.md`
  and point at each file with a one-line "read this when…". For a file over ~300 lines, give
  it a short table of contents.
- Put deterministic, repeated work into `scripts/`. If every run would otherwise write the
  same helper, bundle it once and call it. Scripts run without loading their source into
  context.
- Organize multi-variant skills by variant so the agent reads only the relevant file:
  `references/aws.md`, `references/gcp.md`, etc.

## Writing style

- Imperative instructions. Explain the _why_ behind each one — modern models follow reasoned
  guidance better than bare rules. Reserve ALL-CAPS MUSTs for genuine invariants; if you are
  reaching for them often, reframe and explain instead.
- Give input→output examples for anything with a fixed format.
- Write the body agent-neutrally. Describe intent ("delegate exploration to a subagent",
  "run a deterministic check before editing"), not a specific agent's call. The adapters bind
  intent to each agent's mechanism.

## Specify before you write (AI-gap self-test)

Before drafting, pin down the five things an under-specified skill leaves to chance, because
an agent takes the most literal reading of anything unsaid:

1. Valid inputs (types, ranges, empty/missing handling).
2. Expected output — the exact definition of "done".
3. Failure handling — what counts as failure and what to do then.
4. Scope limits — what the skill must not do.
5. Dependencies — what each external tool/command is assumed to provide.

Then ask: "if an agent followed this skill and produced something wrong, what did I leave
unspecified?" Add that constraint now. This is cheaper than discovering it in evals.

## Portability checklist

- [ ] `name` matches the directory and the regex; `description` is present, under 1024 chars,
      no angle brackets, and states both what and when (plus when-not).
- [ ] No non-portable frontmatter keys in the core (`allowed-tools`, `context`, `paths`,
      `disable-model-invocation`, `agent`, `model`, … are Claude-specific; keep in adapters).
- [ ] Body has no hard-coded agent tool calls (`Task`, `@"x (agent)"`, `skill({...})`).
- [ ] References use relative paths; scripts declare their interpreter and are executable.
- [ ] Runs assuming only a POSIX shell and the bundled languages; no provider/model assumption.

Run `scripts/validate_skill.py <skill-dir>` for a fast automated pass over most of this.
