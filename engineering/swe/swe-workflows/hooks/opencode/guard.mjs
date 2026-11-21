// OpenCode guardrail for swe-workflows: block an integration action when the shared policy-gate
// blocks it. OpenCode "plugins" are JS/TS modules returning a hooks object; THROWING in
// `tool.execute.before` blocks the tool call. All logic lives in ../gate.sh, shared with the
// Claude Code and oh-my-pi overlays so the four never drift.
//
// Install: drop (or symlink) this file into `.opencode/plugins/` (project) or the user plugin
// dir, or reference it via the `plugin` config key. (MCP tool calls historically did not fire
// plugin hooks — verify against your OpenCode build.)
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const gate = join(dirname(fileURLToPath(import.meta.url)), "..", "gate.sh"); // hooks/gate.sh

export const SweProcessGuard = async () => ({
  "tool.execute.before": async (input, _output) => {
    // The command text lives somewhere in `input`; stringify the whole thing so gate.sh can
    // match the boundary without us knowing OpenCode's exact payload shape.
    const r = spawnSync("sh", [gate], {
      input: JSON.stringify(input ?? {}),
      encoding: "utf8",
    });
    if (typeof r.status === "number" && r.status !== 0) {
      throw new Error(
        (r.stderr || "").trim() ||
          "swe-workflows policy-gate blocked this action",
      );
    }
  },
});
