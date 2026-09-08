// code-quality:measure — Claude-native workflow.
//
// Not invoked automatically. SKILL.md instructs Claude Code to pass this
// file's contents to the Workflow tool (Workflow({script: <this file>}))
// only when the user has opted into multi-agent orchestration — see
// SKILL.md's "Running this across agent hosts" section for why.
//
// Two phases:
//   1. Run metrics — one agent locates the skill's own assets/run.sh
//      (discovery + parallel per-metric fan-out + summary all happen
//      inside that deterministic script, not here) and extracts every
//      finding that crossed its metric's own printed threshold.
//   2. Verify findings — one skeptic subagent per finding, in parallel,
//      scoring confidence that it's a genuine risk rather than a false
//      positive or acceptable complexity. Mirrors the fan-out-then-verify
//      pattern this org's own code-review workflow uses.
//
// This is the equivalent of the opencode/ command + measure-verify agent
// pair in this same skill package — same two phases, expressed with
// Claude Code's own orchestration primitives instead of opencode's.

export const meta = {
  name: "code-quality-measure",
  description:
    "Run code-quality:measure, then adversarially verify every flagged finding before reporting it",
  phases: [
    {
      title: "Run metrics",
      detail:
        "assets/run.sh's discovery + parallel per-metric fan-out, then extract findings",
    },
    {
      title: "Verify findings",
      detail:
        "one skeptic subagent per flagged finding, filters false positives",
    },
  ],
};

const FINDINGS_SCHEMA = {
  type: "object",
  properties: {
    scope_note: { type: "string" },
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          metric: { type: "string" },
          file: { type: "string" },
          function: { type: ["string", "null"] },
          line: { type: ["number", "null"] },
          score: { type: "number" },
          threshold: { type: "number" },
        },
        required: ["metric", "file", "score", "threshold"],
      },
    },
  },
  required: ["findings"],
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    confidence: { type: "number" },
    reasoning: { type: "string" },
  },
  required: ["confidence", "reasoning"],
};

phase(meta.phases[0].title);
// No Rust-specific (or any language-specific) default here on purpose — by the
// time SKILL.md decides to invoke this workflow, it has already detected the
// language and its manifest (step 1 of the Process section). Guessing a
// filename here would bake one language's convention into a script meant to
// work identically for all of them.
const target = args && args.manifestPath;
if (!target) {
  throw new Error(
    "measure.workflow.js requires args.manifestPath — the manifest SKILL.md's own language-detection step already found.",
  );
}
// Workflow scripts can't read the filesystem directly, only agents can — so
// locating this skill's own assets/run.sh normally means asking an agent to
// search likely install paths. Pass args.skillRoot (the directory containing
// this SKILL.md, which the caller already knows) to skip that search.
const skillRoot = args && args.skillRoot;
const runInstruction = skillRoot
  ? `Run \`${skillRoot}/assets/run.sh ${target}\`.`
  : `Locate the code-quality:measure skill's own directory — it contains assets/run.sh
     under a code-quality/workflows/measure path (check .claude/skills/measure,
     ~/.claude/skills/measure, or search for a directory matching that layout) — and run
     \`assets/run.sh ${target}\`.`;
const report = await agent(
  `${runInstruction}

   That script prints a discovery minireport (which metrics are [available] vs [missing]),
   then runs every available metric in parallel, then a per-metric summary. Metric names and
   thresholds vary by language — don't assume any specific ones, read whatever the script's own
   output names and use its own printed threshold for each. Extract every finding that crossed
   its metric's threshold. For each finding return: metric, file, function (null if not
   applicable), line (null if not applicable), score, threshold.

   Do not fabricate a finding for a metric the discovery step reported [missing] — note that
   in scope_note instead. If nothing crossed a threshold, return an empty findings array.`,
  {
    label: "run-and-parse",
    phase: meta.phases[0].title,
    schema: FINDINGS_SCHEMA,
  },
);

phase(meta.phases[1].title);
// The judging criteria live in one place, references/verify-rubric.md — read at
// runtime by both this workflow's verify agent and OpenCode's measure-verify.md,
// instead of being copy-pasted into each (a JS template literal and a markdown
// agent file share no runtime that could import a common module).
const rubricInstruction = skillRoot
  ? `Read \`${skillRoot}/references/verify-rubric.md\` and follow it exactly.`
  : `Locate the code-quality:measure skill's own directory (same lookup as above)
     and read \`references/verify-rubric.md\` from it, then follow it exactly.`;
const verified = await parallel(
  report.findings.map((f) => async () => {
    const verdict = await agent(
      `${rubricInstruction}

       Manifest: ${target}. Metric: ${f.metric}. File: ${f.file}. Function: ${f.function || "n/a"}. Line: ${f.line ?? "n/a"}.
       Score: ${f.score} (threshold ${f.threshold}).`,
      {
        label: `verify:${f.file}`,
        phase: meta.phases[1].title,
        schema: VERDICT_SCHEMA,
      },
    );
    return { ...f, verdict };
  }),
);

const confirmed = verified
  .filter(Boolean)
  .filter((f) => f.verdict.confidence >= 80);
log(
  `${confirmed.length}/${report.findings.length} findings confirmed at confidence >= 80`,
);

return { scope_note: report.scope_note || null, confirmed, all: verified };
