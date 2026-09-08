// code-quality:comments — Claude-native workflow.
//
// Not invoked automatically. SKILL.md instructs Claude Code to pass this file's
// contents to the Workflow tool (Workflow({script: <this file>})) only when the
// user has opted into multi-agent orchestration — see SKILL.md's "Running the
// `comments` workflow across hosts" section for why.
//
// One phase, unlike `measure`'s two: there's no deterministic tool to run first —
// judging comment quality is inherently a read-through, so each file gets one
// subagent doing the reading and the judging in the same step. One subagent per
// file, in parallel — "a separate sub agent" per file, not one agent reading every
// file in sequence.
//
// This is the equivalent of the opencode/agent/comment-quality.md subagent in this
// same skill package — same rubric (references/comment-rubric.md), expressed with
// Claude Code's own orchestration primitives instead of opencode's.

export const meta = {
  name: "code-quality-comments",
  description:
    "Judge comment quality (necessity, verbosity, public-API coverage) across one or more files, one subagent per file",
  phases: [
    {
      title: "Judge comments",
      detail: "one subagent per file, reading references/comment-rubric.md",
    },
  ],
};

const VIOLATIONS_SCHEMA = {
  type: "object",
  properties: {
    violations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          line: { type: "number" },
          excerpt: { type: "string" },
          failure: { type: "string" },
          proposed_fix: { type: "string" },
        },
        required: ["line", "excerpt", "failure", "proposed_fix"],
      },
    },
  },
  required: ["violations"],
};

phase(meta.phases[0].title);
const filePaths = args && args.filePaths;
if (!Array.isArray(filePaths) || filePaths.length === 0) {
  throw new Error(
    "comments.workflow.js requires args.filePaths (a non-empty array) — the files to judge.",
  );
}
// Workflow scripts can't read the filesystem directly, only agents can — so
// locating this skill's own references/comment-rubric.md normally means asking an
// agent to search likely install paths. Pass args.skillRoot (the directory
// containing this SKILL.md, which the caller already knows) to skip that search.
const skillRoot = args && args.skillRoot;
const rubricInstruction = skillRoot
  ? `Read \`${skillRoot}/references/comment-rubric.md\` and follow it exactly.`
  : `Locate the code-quality:measure skill's own directory — it contains
     references/comment-rubric.md under a code-quality/workflows/measure path (check
     .claude/skills/measure, ~/.claude/skills/measure, or search for a directory
     matching that layout) — and read references/comment-rubric.md from it, then
     follow it exactly.`;

const results = await parallel(
  filePaths.map((file) => async () => {
    const result = await agent(
      `${rubricInstruction}

       File to judge: ${file}.`,
      {
        label: `judge:${file}`,
        phase: meta.phases[0].title,
        schema: VIOLATIONS_SCHEMA,
      },
    );
    return { file, violations: result.violations };
  }),
);

const flagged = results.filter(Boolean).filter((r) => r.violations.length > 0);
log(
  `${flagged.length}/${filePaths.length} file(s) have comment-quality violations`,
);

return { results };
