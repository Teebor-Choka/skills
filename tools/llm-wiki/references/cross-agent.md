# Cross-agent dispatch for wiki subagent workflows

Read this only when a wiki is large enough that serial ingestion or single-pass querying is the
bottleneck. Small and medium wikis need none of it — do the work in one agent. The two workflows
worth parallelizing are named in `SKILL.md`; this file binds each to Claude Code, Codex, and
OpenCode. For the general mechanics of subagents, orchestration, and portability, use the
`skill-creator` skill (`references/workflows.md`); this file is only the wiki-specific wiring.

## The invariant that dictates the shape

`wiki/`, `index.md`, and every `_MOC.md` are **shared mutable state**. Two agents editing them
concurrently corrupt links and orphan checks. So the safe pattern is always the same:

- **Fan out reads and drafts** — reading a source and proposing a page (plus the entity/concept
  edits it implies) is independent per source and parallelizes cleanly.
- **Merge writes serially** — one agent applies the proposals, resolving link and `_MOC.md`
  conflicts, then runs `bash .ci/check-all.sh` once at the end.

Give each read-only ingester a tight brief: the source path, the current area taxonomy, and the
existing page slugs it may link to, so its proposed `[[wikilinks]]` resolve on merge.

## Workflow A — parallel ingestion

Fan out one read-only subagent per source; each returns a proposed `source-note` plus a list of
entity/concept pages to touch. The main agent merges them one at a time, then runs CI.

### Claude Code

- **Parallel drafts** — issue several `Agent` tool calls in one turn (or a `general-purpose`
  subagent per source), each with tools limited to read/grep. Have each return the page body and
  proposed edits as text; do not let subagents write into `wiki/`.
- **Deterministic pipeline** — for a fixed batch, the `Workflow` tool expresses it directly:
  `parallel()` the ingesters, then a single `agent()` merge-and-CI stage. Keep this in the Claude
  adapter, never in the portable `SKILL.md` body.
- Optional guaranteed entry: a `.claude/commands/ingest-batch.md` that says "use the `llm-wiki`
  skill to ingest $ARGUMENTS in parallel, then merge and run CI".

### Codex

- Launch one `codex exec` per source with a read-only sandbox, capturing each proposal:
  ```bash
  for f in raw/batch/*.md; do
    codex exec --json -s read-only -o "proposals/$(basename "$f").txt" \
      "\$llm-wiki: draft a source-note and the entity/concept edits for $f. Do not write files." &
  done
  wait
  ```
- Then a single writer pass merges and runs CI:
  ```bash
  codex exec -s workspace-write "\$llm-wiki: apply the proposals in proposals/, fix links, run .ci/check-all.sh"
  ```
- Role-specialized subagents work too (a read-only ingester config vs a writer config).

### OpenCode

- Use the `task` tool or `@`-mention a read-only subagent (`mode: subagent`, `permission: { edit:
deny }`) once per source; collect the proposals.
- Or drive it headless, one process per source, then a single writer run:
  ```bash
  for f in raw/batch/*.md; do
    opencode run -q -f json --agent plan "Use llm-wiki to draft a page + edits for $f (no writes)" \
      > "proposals/$(basename "$f").json" &
  done
  wait
  opencode run --auto --agent build "Use llm-wiki to merge proposals/, fix links, run .ci/check-all.sh"
  ```

## Workflow B — multi-hop query with verification

Draft the answer, then have a **separate, adversarial reader** confirm every `[[wikilink]]`
citation actually supports its claim before the answer is filed back as a page. This enforces the
no-fabrication rule with a fresh pair of eyes rather than trusting the drafter's own links.

### Claude Code

Two `agent()` stages in a `Workflow`, or two turns: a `general-purpose` researcher drafts with
citations; a second read-only subagent (its brief: "for each `[[link]]`, open the page and confirm
it supports the sentence; list any that do not") verifies. File the page only after it passes.

### Codex

```bash
codex exec -o answer.txt "\$llm-wiki: answer <Q>, cite every claim with [[wikilinks]]"
codex exec -s read-only "\$llm-wiki: verify each [[link]] in answer.txt supports its claim; list failures"
```

Resume the first session (`codex exec resume --last`) to fix failures, then file the page.

### OpenCode

A read-only reviewer subagent checks the draft: `@reviewer verify the citations in the draft`, or
headless `opencode run --agent plan "verify each [[link]] supports its claim"`. Only after it
passes does a `build`-agent run write the `synthesis`/`concept` page and run CI.

## When to stop orchestrating

Delegation costs tokens and a merge step. Use it when sources number in the dozens or a question
truly spans many areas. Below that, a single agent following `SKILL.md` is faster and simpler —
prefer it.
