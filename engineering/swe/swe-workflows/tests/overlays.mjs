// overlays.mjs — contract test for the native hook overlays (OpenCode, oh-my-pi).
//
// gate.sh is proven end-to-end by the bats suite (gate.bats, forge-state.bats). The two JS
// overlays are thin shims that each spawn gate.sh and must translate its exit code into THAT
// harness's veto signal:
//   - OpenCode guard.mjs: THROW in `tool.execute.before` blocks the tool call.
//   - oh-my-pi policy-gate.mjs: return `{ block: true }` from the `tool_call` pre-handler.
// This test pins that translation. It is hermetic: each overlay is copied beside a stub gate.sh
// whose exit code we control (STUB_EXIT), so no gh, policy skill, or network is touched. A
// side effect is proving the overlays' only local dependency is ../gate.sh (a copy with just the
// stub sibling must still load).
//
// Run: node tests/overlays.mjs   (wired into `nix flake check` as the swe-overlays check)
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  copyFileSync,
  writeFileSync,
  chmodSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url)); // .../swe-workflows/tests
const hooks = join(here, "..", "hooks"); // .../swe-workflows/hooks

// Lay the two overlays beside a controllable stub gate.sh (they resolve ../gate.sh by location).
const root = mkdtempSync(join(tmpdir(), "swe-overlays-"));
mkdirSync(join(root, "hooks", "opencode"), { recursive: true });
mkdirSync(join(root, "hooks", "omp"), { recursive: true });
writeFileSync(
  join(root, "hooks", "gate.sh"),
  "#!/usr/bin/env sh\nexit ${STUB_EXIT:-0}\n",
);
chmodSync(join(root, "hooks", "gate.sh"), 0o755);
copyFileSync(
  join(hooks, "opencode", "guard.mjs"),
  join(root, "hooks", "opencode", "guard.mjs"),
);
copyFileSync(
  join(hooks, "omp", "policy-gate.mjs"),
  join(root, "hooks", "omp", "policy-gate.mjs"),
);

const guardUrl = new URL(
  "file://" + join(root, "hooks", "opencode", "guard.mjs"),
);
const ompUrl = new URL(
  "file://" + join(root, "hooks", "omp", "policy-gate.mjs"),
);

let passed = 0;
let failed = 0;
const check = (name, fn) => {
  try {
    fn();
    passed++;
    console.log("ok   -", name);
  } catch (e) {
    failed++;
    console.log("FAIL -", name, "\n      ", e.message);
  }
};
const acheck = async (name, fn) => {
  try {
    await fn();
    passed++;
    console.log("ok   -", name);
  } catch (e) {
    failed++;
    console.log("FAIL -", name, "\n      ", e.message);
  }
};

// --- OpenCode: guard vetoes by throwing ---
const { SweProcessGuard } = await import(guardUrl);
const before = (await SweProcessGuard())["tool.execute.before"];

await acheck(
  "opencode: gate blocks (exit 1) => tool.execute.before throws (veto)",
  async () => {
    process.env.STUB_EXIT = "1";
    let threw = false;
    try {
      await before({ command: "gh pr merge 7 --squash" }, {});
    } catch {
      threw = true;
    }
    assert.equal(threw, true, "expected a throw to veto the tool call");
  },
);

await acheck("opencode: gate passes (exit 0) => no throw (allow)", async () => {
  process.env.STUB_EXIT = "0";
  let threw = false;
  try {
    await before({ command: "ls -la" }, {});
  } catch {
    threw = true;
  }
  assert.equal(threw, false, "a passing gate must not veto");
});

// --- oh-my-pi: hook vetoes by returning { block: true } ---
const ompHook = (await import(ompUrl)).default;
let handler;
check("omp: registers a tool_call pre-handler", () => {
  ompHook({
    on: (ev, fn) => {
      if (ev === "tool_call") handler = fn;
    },
  });
  assert.equal(
    typeof handler,
    "function",
    "default export must register on tool_call",
  );
});

check("omp: gate blocks (exit 1) => returns { block: true }", () => {
  process.env.STUB_EXIT = "1";
  const r = handler({ input: { command: "gh pr merge 7 --squash" } });
  assert.ok(r && r.block === true, "expected a { block: true } veto object");
});

check("omp: gate passes (exit 0) => returns no veto", () => {
  process.env.STUB_EXIT = "0";
  const r = handler({ input: { command: "ls -la" } });
  assert.ok(!r || r.block !== true, "a passing gate must not return a block");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
