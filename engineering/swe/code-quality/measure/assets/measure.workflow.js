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
const target = (args && args.manifestPath) || "Cargo.toml";
// Workflow scripts can't read the filesystem directly, only agents can — so
// locating this skill's own assets/run.sh normally means asking an agent to
// search likely install paths. Pass args.skillRoot (the directory containing
// this SKILL.md, which the caller already knows) to skip that search.
const skillRoot = args && args.skillRoot;
const runInstruction = skillRoot
  ? `Run \`${skillRoot}/assets/run.sh ${target}\`.`
  : `Locate the code-quality:measure skill's own directory — it contains assets/rust/run.sh
     under a code-quality/measure path (check .claude/skills/measure, ~/.claude/skills/measure,
     or search for a directory matching that layout) — and run \`assets/run.sh ${target}\`.`;
const report = await agent(
  `${runInstruction}

   That script prints a discovery minireport (which metrics are [available] vs [missing]),
   then runs every available metric in parallel, then a per-metric summary. Read its output
   and extract every finding that crossed its own printed threshold (CRAP score above the
   printed threshold, FileRisk above the printed threshold). For each finding return: metric,
   file, function (null if not applicable), line (null if not applicable), score, threshold.

   Do not fabricate a finding for a metric the discovery step reported [missing] — note that
   in scope_note instead. If nothing crossed a threshold, return an empty findings array.`,
  {
    label: "run-and-parse",
    phase: meta.phases[0].title,
    schema: FINDINGS_SCHEMA,
  },
);

phase(meta.phases[1].title);
// This rubric is duplicated in ../opencode/agent/measure-verify.md, since a JS
// template literal and a markdown agent file share no runtime to factor it
// into. Keep the two in sync by hand if the judgment criteria change.
const verified = await parallel(
  report.findings.map((f) => async () => {
    const verdict = await agent(
      `Judge this code-quality:measure finding with a skeptic's eye. Default to LOW confidence
       unless you have good reason to trust it.

       Manifest: ${target}. Metric: ${f.metric}. File: ${f.file}. Function: ${f.function || "n/a"}. Line: ${f.line ?? "n/a"}.
       Score: ${f.score} (threshold ${f.threshold}).

       Read the actual file/function this finding names. Score confidence 0-100 that this is a
       genuine, actionable risk worth fixing — not acceptable/inherent complexity, not a false
       positive. Give one sentence of reasoning.`,
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
