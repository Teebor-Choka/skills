# Running the audit natively on each agent

SKILL.md describes the audit as portable intent: fan out over independent dimensions, then
verify each flagged finding before synthesizing one report. This file binds that intent to
each agent's own primitives. The deterministic core is identical everywhere — `assets/run.sh`
(and `assets/report.sh`) is plain shell that any human, CI job, or agent runs the same way.
What differs is only the agent layer on top: the parallel fan-out of reviewers and the skeptic
verify pass.

For general cross-agent mechanics (subagent definitions, orchestration, headless/CI
invocation), see the skill-creator references — this file does not duplicate them:

- `model/tools/skill-creator/references/workflows.md` — subagents, parallel fan-out,
  orchestration per agent.
- `model/tools/skill-creator/references/platforms/{claude-code,codex,opencode}.md` — exact
  file formats and flags.

Two things are shared across every agent and read at runtime, so there is exactly one copy of
each rather than an embedded duplicate per host:

- [verify-rubric.md](verify-rubric.md) — how the skeptic pass scores a `measure` finding.
- [comment-rubric.md](comment-rubric.md) — how a `comments` reviewer judges one file.

Resolve this skill's own directory first on every host and pass it as `skillRoot` /
`$SKILL_DIR` — a subagent or workflow script cannot locate the skill's assets by itself; only
the driving agent knows where the skill is installed.

## `measure` — run metrics, then verify each finding

Two phases: (1) one agent runs `assets/run.sh`, parses its JSON, and extracts the findings
(row's own `flagged` field if present; else the row's primary value vs. the envelope
`threshold`; else, for a threshold-less metric, the rows that stand out — never a metric that
`discovery.missing` lists); (2) one skeptic subagent per finding, in parallel, scoring
confidence per [verify-rubric.md](verify-rubric.md), keeping only the confident ones (the
bundled workflows use confidence ≥ 80).

### Claude Code

Use the **Workflow** tool for the full deterministic find → verify → synthesize pipeline. It
is opt-in per that tool's own usage rules. Pass the script file's contents plus the manifests
SKILL.md's language-detection step already found and this skill's resolved directory:

```
Workflow({
  script: <contents of assets/measure.workflow.js>,
  args: { manifestPaths: ["<path>", ...], skillRoot: "<this skill's directory>" }
})
```

`assets/measure.workflow.js` runs `assets/run.sh`, extracts findings, then fans a skeptic
**agent** out per finding with `parallel()` and returns the confirmed set. For a lighter pass
without the workflow, dispatch the **Agent** tool directly: one call to run and parse
`assets/run.sh`, then several Agent calls in one turn — one skeptic per finding — each pointed
at [verify-rubric.md](verify-rubric.md).

### Codex

No scripting engine, so orchestrate through the shell. Run the metrics headless, then fan out
verify with parallel `codex exec` processes and collect their final messages:

```bash
codex exec -o metrics.json "Run <skillRoot>/assets/run.sh --manifest <path>; print only its JSON."
# then, per finding, in parallel:
codex exec -o "verify-$i.txt" "Read <skillRoot>/references/verify-rubric.md and follow it for: <finding>"
```

Give each verify a role-specialized subagent (read-only, no edit) if you have one configured;
otherwise the plain `codex exec` above suffices. Keep confirmed findings above your confidence
bar and synthesize the report in a final call.

### OpenCode

The `/code-quality` command (`opencode/command/code-quality.md`) describes the whole toolkit
to the `build` agent and lets it use whichever piece the request needs — a full audit, one
metric, or a single spot-check. For the verify pass it dispatches the **`measure-verify`**
subagent (`opencode/agent/measure-verify.md`, `edit: deny`) once per finding via the `task`
tool, each reading [verify-rubric.md](verify-rubric.md). Headless:

```bash
opencode run --auto -q --agent build "Use the code-quality toolkit to audit <path> and verify every finding."
```

### Any other host

Fall back to SKILL.md's inline step 5: run `assets/run.sh`, then spot-check the
highest-scoring finding per metric by hand against [verify-rubric.md](verify-rubric.md). No
orchestration primitive is required — only the confidence discipline.

## `comments` — one reviewer per file, in parallel

One phase, no deterministic tool: each file gets one reviewer that reads
[comment-rubric.md](comment-rubric.md) and judges that file. Fan out one per file.

### Claude Code

```
Workflow({
  script: <contents of assets/comments.workflow.js>,
  args: { filePaths: ["<path>", ...], skillRoot: "<this skill's directory>" }
})
```

`assets/comments.workflow.js` fans one **agent** out per file with `parallel()`, each reading
[comment-rubric.md](comment-rubric.md), and returns the per-file violations. Without the
workflow, make several Agent calls in one turn — one per file — pointed at the same rubric.

### Codex

One `codex exec` per file, in parallel, each instructed to read
`<skillRoot>/references/comment-rubric.md` and judge that one file; collect the outputs.

### OpenCode

The **`comment-quality`** subagent (`opencode/agent/comment-quality.md`, `edit: deny`),
dispatched once per file from the `/code-quality` command or directly, each reading
[comment-rubric.md](comment-rubric.md).

### Any other host

Dispatch a subagent per file directly, pointed at [comment-rubric.md](comment-rubric.md).
There is no deterministic fallback the way `measure` has one, since this workflow has no
non-agent step at all.

## Parity note

The Claude Code workflows and the OpenCode command/agents are two expressions of the same two
phases and the same rubrics — keep them in step when either changes. The OpenCode adapters are
written against OpenCode's documented schema but were not run end-to-end (no OpenCode install
was available to test against); verify against your installed version before relying on them.
