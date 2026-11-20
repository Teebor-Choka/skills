#!/usr/bin/env python3
"""Harness adapter contract and the `agent-run` program (spec 7.8, 8.2, 6.1). Standard library only.

U13a starts `agent-run` by argv exec and appends `--role <role> --brief <path>` from `metadata.org`. The
only other argument is `--isolated`. Everything else comes from the runtime environment:

    ORG_ROOT          org root directory (briefs/, criteria/, manifest.json or manifest.yaml)
    ORG_RUN           run id
    ORG_KEY           full key of the task
    ORG_SESSION_DIR   directory for the per-run history and the call record (required)
    ORG_ITEM          rubric item index (required when the brief is under criteria/)
    ORG_PARENT_ROLE   role that starts this one (optional; enforces `may-spawn`)
    ORG_HARNESS       claude-code (default) or scripted
    ORG_HARNESS_SCRIPT  JSON list of canned replies for the scripted harness

ORG_SESSION_DIR, ORG_ITEM, ORG_PARENT_ROLE, ORG_HARNESS and ORG_HARNESS_SCRIPT are PROVISIONAL names: the
spec fixes the argv only.

Output: one JSON outcome on stdout (`outcome` in contracts/harness.json). Exit 0 ok, 1 refused or failed
(`agent-run: <code>: <message>` on stderr), 2 bad arguments.

Every model call is timed and its cost recorded. A call whose adapter reports no usable cost is refused
(`no-metric`). A refusal before the adapter runs (role, spawn, brief) starts no call and records nothing.
"""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from op_conformance import PARTS, PortError, _probes, _shape, check_schema  # noqa: E402
from validate_catalog import file_under_root, load_document, relative_path_ok  # noqa: E402

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "harness.json"
HARNESS_GUARANTEES = ("context-only", "cost-reported", "refuses-untrusted-on-macos")
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VERDICT_LINE = re.compile(r"^\s*VERDICT:\s*(pass|fail)\s*$", re.IGNORECASE)
DEFAULT_TIMEOUT = 3600

_contract_cache = []


def load_contract():
    if not _contract_cache:
        _contract_cache.append(json.loads(CONTRACT_PATH.read_text()))
    return _contract_cache[0]


# ------------------------------------------------------------------ contract validator


def _validate_contract(doc):
    if not isinstance(doc, dict):
        return ["contract: must be an object"]
    if doc.get("port") != "Harness":
        return [f"contract: unknown port {doc.get('port')!r}"]
    ops = doc.get("operations")
    if not isinstance(ops, dict):
        return ["Harness: operations must be an object"]
    errs = []
    if list(ops) != ["run"]:
        errs.append("Harness: operations must be exactly ['run']")
    op = ops.get("run")
    if not isinstance(op, dict):
        errs.append("Harness.run: must be an object")
    else:
        where = "Harness.run"
        errs += [f"{where}: missing part: {p}" for p in PARTS if p not in op]
        for part in ("input", "output"):
            if part in op:
                errs += _shape(op[part], f"{where}: {part}")
                if isinstance(op[part], dict) and op[part].get("type") != "object":
                    errs.append(f"{where}: {part} must be an object schema")
        guar = op.get("guarantees")
        if "guarantees" in op:
            if not isinstance(guar, list) or not all(isinstance(g, str) for g in guar):
                errs.append(f"{where}: guarantees must be a list of strings")
            else:
                errs += [f"{where}: guarantee '{g}' has no conformance test" for g in guar if g not in HARNESS_GUARANTEES]
                errs += [f"{where}: guarantee '{g}' is required" for g in HARNESS_GUARANTEES if g not in guar]
        codes = op.get("errors")
        if "errors" in op and (not isinstance(codes, list) or "invalid-input" not in codes):
            errs.append(f"{where}: errors must be a list that includes 'invalid-input'")
    if "outcome" not in doc:
        errs.append("Harness: missing outcome")
    else:
        errs += _shape(doc["outcome"], "Harness: outcome")
    return errs


def validate_harness_contract(doc):
    """Return the errors that make the harness contract unusable. Empty list means valid. Never raises."""
    try:
        return _validate_contract(doc)
    except Exception as e:  # noqa: BLE001
        return [f"contract: validator error: {type(e).__name__}: {e}"]


# ------------------------------------------------------------------ prompt and adapters


def build_prompt(brief, context, task):
    """The exact text sent to the model: the brief, the context given, the task. Nothing else."""
    parts = [brief.rstrip()]
    if context:
        parts.append("## Context\n" + "\n".join(f"{c['role']}: {c['text']}" for c in context))
    lines = [f"run: {task['run']}", f"task: {task['task']}"]
    if "item" in task:
        lines.append(f"item: {task['item']}")
    parts.append("## Task\n" + "\n".join(lines))
    if "item" in task:
        parts.append("## Verdict\nEnd your answer with one line: VERDICT: pass or VERDICT: fail.")
    return "\n\n".join(parts)


class _Adapter:
    """Shared input checks. `platform` is injectable so the macOS rule is testable anywhere."""

    def __init__(self, platform=None):
        self.platform = platform or sys.platform

    def _accept(self, op, inp):
        if op != "run":
            raise PortError("invalid-input", f"unknown operation {op!r}")
        bad = check_schema(inp, load_contract()["operations"]["run"]["input"])
        if bad:
            raise PortError("invalid-input", bad[0])
        if inp["isolated"] and inp["context"]:
            raise PortError("invalid-input", "isolated call must have an empty context")
        if inp["trust"] == "untrusted" and self.platform == "darwin":
            raise PortError("refused-untrusted", "untrusted work is not run on macOS")


class ScriptedAdapter(_Adapter):
    """Replays canned replies. A reply key overrides the default; a `None` value removes the key."""

    def __init__(self, script=None, platform=None):
        super().__init__(platform)
        self.script = None if script is None else list(script)

    def call(self, op, inp):
        self._accept(op, inp)
        if self.script is None:
            reply = {}
        elif self.script:
            reply = self.script.pop(0)
        else:
            raise PortError("harness-error", "script exhausted")
        out = {
            "prompt": build_prompt(inp["brief"], inp["context"], inp["task"]),
            "result": "ok",
            "cost": {"usd": 0.0, "seconds": 0.0},
        }
        out.update(reply)
        return {k: v for k, v in out.items() if v is not None}


def _default_runner(argv, stdin, timeout):
    p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _num(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


class ClaudeCodeAdapter(_Adapter):
    """Runs `claude -p` once per call: no resumed session, the prompt on stdin, tools by allow-list."""

    def __init__(self, runner=None, claude_bin="claude", platform=None):
        super().__init__(platform)
        self.runner = runner or _default_runner
        self.claude_bin = claude_bin

    def call(self, op, inp):
        self._accept(op, inp)
        argv = [self.claude_bin, "-p", "--output-format", "json", "--no-session-persistence"]
        argv += ["--allowedTools", ",".join(inp["tools"])] if inp["tools"] else ["--tools", ""]
        prompt = build_prompt(inp["brief"], inp["context"], inp["task"])
        try:
            rc, stdout, stderr = self.runner(argv, prompt, inp.get("timeout_seconds", DEFAULT_TIMEOUT))
        except subprocess.TimeoutExpired:
            raise PortError("timeout", "claude did not finish in time") from None
        except FileNotFoundError:
            raise PortError("harness-unavailable", f"cannot run {self.claude_bin}") from None
        except OSError as e:
            raise PortError("harness-unavailable", f"cannot run {self.claude_bin}: {e.strerror}") from None
        if rc != 0:
            raise PortError("harness-error", f"claude exited {rc}: {stderr.strip()[:200]}")
        try:
            body = json.loads(stdout)
        except ValueError:
            raise PortError("harness-error", "claude output is not JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("result"), str):
            raise PortError("harness-error", "claude output has no result text")
        if body.get("is_error"):
            raise PortError("harness-error", f"claude reported an error: {body['result'][:200]}")
        out = {"prompt": prompt, "result": body["result"]}
        usd, ms = body.get("total_cost_usd"), body.get("duration_ms")
        if _num(usd) and _num(ms):
            cost = {"usd": usd, "seconds": ms / 1000}
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            for key in ("input_tokens", "output_tokens"):
                if isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool):
                    cost[key] = usage[key]
            out["cost"] = cost
        if "item" in inp["task"]:
            lines = body["result"].rstrip().splitlines()
            m = VERDICT_LINE.match(lines[-1]) if lines else None
            if m:
                out["verdict"] = m.group(1).lower()
        return out


# ------------------------------------------------------------------ harness conformance


class _Ctx:
    def __init__(self, call, platform):
        self.call, self.platform = call, platform


def _req(**over):
    base = {"role": "reviewer", "brief": "Review the change.", "tools": [], "isolated": False,
            "trust": "trusted", "context": [], "task": {"run": "conformance", "task": "review"}}
    base.update(over)
    return base


def _expect(call, code, inp):
    try:
        call("run", inp)
    except PortError as e:
        assert e.code == code, f"expected error '{code}', got '{e.code}'"
        return
    raise AssertionError(f"expected error '{code}', call succeeded")


def t_context_only(c):
    marker = "CONFORMANCE-MARKER-4172"
    task = {"run": "conformance", "task": "review"}
    ctx = [{"role": "author", "text": marker}]
    shared = c.call("run", _req(context=ctx))
    assert marker in shared["prompt"], "context given to the adapter is missing from the model input"
    assert shared["prompt"] == build_prompt("Review the change.", ctx, task), \
        "model input holds more or less than the brief, the context and the task"
    fresh = c.call("run", _req(isolated=True))
    assert marker not in fresh["prompt"], "an isolated call carries context from an earlier call"
    assert fresh["prompt"] == build_prompt("Review the change.", [], task), \
        "isolated model input holds more than the brief and the task"
    _expect(c.call, "invalid-input", _req(isolated=True, context=ctx))


def t_cost_reported(c):
    for _ in range(2):
        cost = c.call("run", _req())["cost"]
        assert cost["usd"] >= 0 and cost["seconds"] >= 0, "cost is not a non-negative amount"


def t_untrusted(c):
    c.call("run", _req(trust="trusted"))
    if c.platform == "darwin":
        _expect(c.call, "refused-untrusted", _req(trust="untrusted"))
        return
    try:
        c.call("run", _req(trust="untrusted"))
    except PortError as e:
        assert e.code == "refused-untrusted", f"refused untrusted work with '{e.code}'"


HARNESS_TESTS = {
    "context-only": t_context_only,
    "cost-reported": t_cost_reported,
    "refuses-untrusted-on-macos": t_untrusted,
}


def run_harness_conformance(contract, adapter, platform=None):
    """Run the invalid-input probes and every guarantee test. Returns failure strings, empty on a pass."""
    refused = validate_harness_contract(contract)
    if refused:
        return [f"contract: refused: {e}" for e in refused]
    spec = contract["operations"]["run"]
    label, failures = "Harness.run", []

    def call(name, inp):
        bad = check_schema(inp, spec["input"])
        assert not bad, f"harness input: {bad[0]}"
        try:
            out = adapter.call(name, inp)
        except PortError as e:
            assert e.code in spec["errors"], f"undeclared error code '{e.code}'"
            raise
        bad = check_schema(out, spec["output"])
        assert not bad, f"run output: {bad[0]}"
        return out

    for name, probe in _probes(spec["input"]):
        try:
            adapter.call("run", probe)
            failures.append(f"{label}: invalid-input: {name}: accepted")
        except PortError as e:
            if e.code != "invalid-input":
                failures.append(f"{label}: invalid-input: {name}: refused with '{e.code}'")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{label}: invalid-input: {name}: raised {type(e).__name__}: {e}")
    ctx = _Ctx(call, platform or getattr(adapter, "platform", sys.platform))
    for g in spec["guarantees"]:
        try:
            HARNESS_TESTS[g](ctx)
        except AssertionError as e:
            failures.append(f"{label}: {g}: {e}")
        except PortError as e:
            failures.append(f"{label}: {g}: unexpected error {e.code}")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{label}: {g}: raised {type(e).__name__}: {e}")
    return failures


# ------------------------------------------------------------------ session store


class SessionStore:
    """Per-run history (what a later, non-isolated call may see) and the record of every call.

    In memory without a directory; with one, JSON lines in `<run>.history.jsonl` and `<run>.calls.jsonl`.
    """

    def __init__(self, directory=None):
        self.dir = None if directory is None else Path(directory)
        self._mem = {}

    @staticmethod
    def _check(run):
        if not isinstance(run, str) or not RUN_ID.match(run):
            raise PortError("invalid-input", "run id must match [A-Za-z0-9_-]{1,64}")

    def _read(self, run, kind):
        self._check(run)
        if self.dir is None:
            return list(self._mem.get((run, kind), []))
        path = self.dir / f"{run}.{kind}.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def _add(self, run, kind, entry):
        self._check(run)
        if self.dir is None:
            self._mem.setdefault((run, kind), []).append(entry)
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / f"{run}.{kind}.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def history(self, run):
        return self._read(run, "history")

    def calls(self, run):
        return self._read(run, "calls")

    def add_history(self, run, entry):
        self._add(run, "history", entry)

    def add_call(self, run, entry):
        self._add(run, "calls", entry)


# ------------------------------------------------------------------ run_agent


def _cost_ok(cost):
    return isinstance(cost, dict) and all(_num(cost.get(k)) and cost[k] >= 0 for k in ("usd", "seconds"))


def _check_role(role, manifest, parent_role):
    if role == "owner":
        raise PortError("role-refused", "agent-run may not run as owner")
    if manifest is None:
        return
    roles = manifest.get("roles") if isinstance(manifest, dict) else None
    roles = roles if isinstance(roles, dict) else {}
    if role not in roles:
        raise PortError("role-refused", f"role '{role}' is not in the manifest")
    if parent_role is None:
        return
    if parent_role not in roles:
        raise PortError("spawn-refused", f"parent role '{parent_role}' is not in the manifest")
    allowed = roles[parent_role].get("may-spawn", []) if isinstance(roles[parent_role], dict) else []
    if role not in allowed:
        raise PortError("spawn-refused", f"role '{parent_role}' may not spawn '{role}'")


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _judge_output(out, req, rubric):
    """Return (error code, message) for an adapter result, or (None, "") when it can be used."""
    if not isinstance(out, dict):
        return "harness-error", "adapter returned no object"
    if not _cost_ok(out.get("cost")):
        return "no-metric", "adapter reported no usable cost (usd and seconds)"
    bad = check_schema(out, load_contract()["operations"]["run"]["output"])
    if bad:
        return "harness-error", f"adapter output breaks the contract: {bad[0]}"
    if out["prompt"] != build_prompt(req["brief"], req["context"], req["task"]):
        return "harness-error", "model input differs from brief, context and task"
    if rubric and "verdict" not in out:
        return "invalid-verdict", "judge returned no pass or fail verdict"
    return None, ""


def run_agent(adapter, store, *, role, brief, task, isolated, trust="trusted", tools=(), manifest=None,
              parent_role=None, signer=None, rubric=False, clock=time.monotonic, timeout_seconds=None):
    """Run one agent call and return the outcome. Raises PortError on a refusal or a failure.

    `isolated` gives the adapter an empty context. Otherwise it gets the earlier results of the same run.
    """
    _check_role(role, manifest, parent_role)
    run = task["run"]
    if rubric and "item" not in task:
        raise PortError("invalid-input", "a rubric call needs an item index")
    context = [] if isolated else store.history(run)
    req = {"role": role, "brief": brief, "tools": list(tools), "isolated": bool(isolated), "trust": trust,
           "context": context, "task": dict(task)}
    if timeout_seconds is not None:
        req["timeout_seconds"] = timeout_seconds
    started = clock()
    out, code, message = None, None, ""
    try:
        out = adapter.call("run", req)
    except PortError as e:
        code, message = e.code, str(e)
    except Exception as e:  # noqa: BLE001
        code, message = "harness-error", f"{type(e).__name__}: {e}"
    seconds = clock() - started
    if code is None:
        code, message = _judge_output(out, req, rubric)
    spent = isinstance(out, dict) and _cost_ok(out.get("cost"))
    record = {"run": run, "task": task["task"], "role": role, "isolated": bool(isolated), "ok": code is None,
              "seconds": seconds, "usd": out["cost"]["usd"] if spent else None}
    if code is not None:
        record["error"] = code
    store.add_call(run, record)
    if code is not None:
        raise PortError(code, message)
    store.add_history(run, {"role": role, "text": out["result"]})
    cost = {**out["cost"], "seconds": seconds}
    data = {"run": run, "task": task["task"], "role": role, "result": out["result"]}
    if rubric:
        data = {"run": run, "task": task["task"], "item": task["item"], "role": role,
                "verdict": out["verdict"], "result": out["result"]}
    event = {"type": "org.rubric-verdict" if rubric else "org.agent-result", "data": data}
    if signer is not None:
        sig = signer(json.loads(json.dumps(event)))
        if not isinstance(sig, str):
            raise PortError("harness-error", "signer did not return a string")
        event["signature"] = sig
    evidence = [{"name": "prompt", "sha256": _sha(out["prompt"])}, {"name": "result", "sha256": _sha(out["result"])}]
    return {"event": event, "evidence": evidence, "cost": cost}


# ------------------------------------------------------------------ command line


class _BadArguments(Exception):
    pass


def _parse_args(argv):
    seen, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a == "--isolated":
            if "isolated" in seen:
                raise _BadArguments("--isolated given more than once")
            seen["isolated"] = True
            i += 1
        elif a in ("--role", "--brief"):
            key = a[2:]
            if key in seen:
                raise _BadArguments(f"{a} given more than once")
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise _BadArguments(f"{a} needs a value")
            seen[key] = argv[i + 1]
            i += 2
        else:
            raise _BadArguments(f"'{a}' is not allowed (allowed: --isolated, --role, --brief)")
    for key in ("role", "brief"):
        if key not in seen:
            raise _BadArguments(f"--{key} is required")
    return seen["role"], seen["brief"], bool(seen.get("isolated"))


def _read_brief(root, rel):
    if not (relative_path_ok(rel, "briefs/", ".md") or relative_path_ok(rel, "criteria/", ".md")):
        raise PortError("brief-refused", "brief must be a relative path under briefs/ or criteria/ ending .md")
    if not file_under_root(root, rel):
        raise PortError("brief-refused", f"{rel}: not a file inside the org root")
    return Path(root, rel).read_text(encoding="utf-8")


def _load_manifest(root):
    for name in ("manifest.json", "manifest.yaml", "manifest.yml"):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                return load_document(path)
            except Exception as e:  # noqa: BLE001
                raise PortError("invalid-input", f"cannot load {name}: {e}") from None
    raise PortError("invalid-input", "no manifest in the org root")


def _make_adapter(env):
    name = env.get("ORG_HARNESS", "claude-code")
    if name == "claude-code":
        return ClaudeCodeAdapter()
    if name == "scripted":
        path = env.get("ORG_HARNESS_SCRIPT")
        try:
            script = json.loads(Path(path).read_text()) if path else None
        except (OSError, ValueError):
            raise PortError("harness-unavailable", "cannot read ORG_HARNESS_SCRIPT") from None
        return ScriptedAdapter(script=script)
    raise PortError("harness-unavailable", f"unknown harness '{name}'")


def main(argv, env=None, stdout=None, stderr=None):
    env = os.environ if env is None else env
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    try:
        role, brief_path, isolated = _parse_args(list(argv))
    except _BadArguments as e:
        print(f"agent-run: bad-arguments: {e}", file=stderr)
        return 2
    try:
        for name in ("ORG_ROOT", "ORG_RUN", "ORG_KEY"):
            if not env.get(name):
                raise PortError("invalid-input", f"{name} is not set")
        if not env.get("ORG_SESSION_DIR"):
            raise PortError("no-record-dir", "ORG_SESSION_DIR is not set; every call must be recorded")
        root = env["ORG_ROOT"]
        brief = _read_brief(root, brief_path)
        rubric = brief_path.startswith("criteria/")
        task = {"run": env["ORG_RUN"], "task": env["ORG_KEY"]}
        if rubric:
            item = env.get("ORG_ITEM", "")
            if not item.isdigit():
                raise PortError("invalid-input", "a rubric brief needs ORG_ITEM, the item index")
            task["item"] = int(item)
        adapter = _make_adapter(env)
        outcome = run_agent(
            adapter, SessionStore(env["ORG_SESSION_DIR"]), role=role, brief=brief, task=task, isolated=isolated,
            manifest=_load_manifest(root), parent_role=env.get("ORG_PARENT_ROLE") or None, rubric=rubric)
    except PortError as e:
        print(f"agent-run: {e}", file=stderr)
        return 1
    print(json.dumps(outcome), file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
