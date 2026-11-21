// oh-my-pi native guardrail for swe-workflows: block an integration action when the shared
// policy-gate blocks it. A thin overlay — all the logic is in ../gate.sh, shared with the
// Claude Code hook, so the two never drift.
//
// oh-my-pi hooks are JS/TS factories discovered under `.omp/hooks/pre/` or an installed
// plugin; `export default function hook(pi)` registers on events via `pi.on(...)`, and the
// `tool_call` (pre) event can veto the call. The exact veto shape moves fast across oh-my-pi
// builds — verify `block`/`veto`/return-value against the installed version before relying on
// a hard block; the WARN path (mode:single) is correct regardless.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const gate = join(here, "..", "gate.sh"); // hooks/gate.sh, one level up from hooks/omp/

export default function hook(pi) {
  pi.on("tool_call", (ev) => {
    const payload = JSON.stringify(ev?.input ?? ev ?? {});
    const r = spawnSync("sh", [gate], { input: payload, encoding: "utf8" });
    if (typeof r.status === "number" && r.status !== 0) {
      return {
        block: true,
        reason:
          (r.stderr || "").trim() ||
          "swe-workflows policy-gate blocked this action",
      };
    }
  });
}
