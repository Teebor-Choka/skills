#!/usr/bin/env python3
"""Harness adapter contract and the `agent-run` program (spec 7.8, 8.2, 6.1). Standard library only.

U13a starts `agent-run` by argv exec and appends `--role <role> --brief <path>` from `metadata.org`,
`--network <policy>` when the step has one (P19) and `--input <path>`, the runtime-owned task input file
(P14). The only other argument is `--isolated`.

The network policy is REQUESTED from the instance tool: it is enforced only by a real instance tool, and none
exists yet. The call record says `enforced: false`. The model child runs with an allow-listed environment
(CHILD_ENV_ALLOW plus the names in ORG_CHILD_ENV_ALLOW), an empty temp directory as cwd, no ORG_* variable but
ORG_PARENT_ROLE, and the flags in ISOLATION_FLAGS. Of those flags only `claude --help` was read, not run. Everything else comes from the runtime environment:

    ORG_ROOT          org root directory (briefs/, criteria/, manifest.json or manifest.yaml)
    ORG_RUN           run id
    ORG_KEY           full key of the task
    ORG_SESSION_DIR   directory for the per-run history and the call record (required, outside ORG_ROOT)
    ORG_ITEM          rubric item index (required when the brief is under criteria/)
    ORG_PARENT_ROLE   role that starts this one (absent for the top-level launch; enforces `may-spawn`)
    ORG_TRUST         trusted (default) or untrusted; set by the runtime
    ORG_CHILD_ENV_ALLOW  extra variable names the model child may inherit
    ORG_TEST_HARNESS  1 allows ORG_HARNESS=scripted and ORG_INSTANCES=scripted (tests only)
    ORG_INSTANCES     instance tool for --network; only `scripted` exists so far
    ORG_NETWORK_POLICIES  JSON map of policy name to {mode, allow}, for --network
    ORG_HARNESS       claude-code (default) or scripted
    ORG_HARNESS_SCRIPT  JSON list of canned replies for the scripted harness

ORG_SESSION_DIR, ORG_ITEM, ORG_PARENT_ROLE, ORG_HARNESS, ORG_HARNESS_SCRIPT, ORG_INSTANCES and
ORG_NETWORK_POLICIES are PROVISIONAL names: the
spec fixes the argv only.

Output: one JSON outcome on stdout (`outcome` in contracts/harness.json). Exit 0 ok, 1 refused or failed
(`agent-run: <code>: <message>` on stderr), 2 bad arguments.

Every model call is timed and its cost recorded. A call whose adapter reports no usable cost is refused
(`no-metric`). A refusal before the adapter runs (role, spawn, brief) starts no call and records nothing.
"""
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from op_conformance import PARTS, PortError, _probes, _shape, check_schema  # noqa: E402
from validate_catalog import LoadError, _check_json_nesting, load_document, relative_path_ok  # noqa: E402

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "harness" / "harness.json"
HARNESS_GUARANTEES = ("context-only", "cost-reported", "refuses-untrusted-on-macos", "task-input-in-prompt")
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VERDICT_LINE = re.compile(r"^\s*VERDICT:\s*(pass|fail)\s*$", re.IGNORECASE)
DEFAULT_TIMEOUT = 3000  # below the 1 hour step limit, so the program kills its child before the runtime does
CHILD_ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "TERM", "HOME", "TMPDIR", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                   "CLAUDE_CODE_OAUTH_TOKEN")
# Flags read from `claude --help` (2.1.311); not run here. --safe-mode: no CLAUDE.md, skills, plugins, hooks, MCP
# servers or custom commands, auth still works (--bare would drop OAuth and keychain).
ISOLATION_FLAGS = ("--safe-mode", "--strict-mcp-config", "--disable-slash-commands")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Terminated(BaseException):
    """Raised by the SIGTERM handler. A BaseException so no adapter swallows it."""

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


def build_prompt(brief, context, task, task_input=None, reasons=None):
    """The exact text sent to the model: brief, context, task, task input, reasons. Nothing else.

    Everything but the brief is JSON, so no value an author wrote can open a section or name another role.
    """
    parts = [brief.rstrip()]
    if context:
        parts.append("## Context (JSON)\n" + json.dumps(context, sort_keys=True))
    parts.append("## Task\n" + json.dumps(task, sort_keys=True))
    if task_input:
        parts.append("## Input\n" + task_input)
    if reasons:
        parts.append("## Reasons (JSON)\n" + json.dumps(reasons, sort_keys=True))
    if "item" in task:
        parts.append("## Verdict\nEnd your answer with one line: VERDICT: pass or VERDICT: fail.")
    return "\n\n".join(parts)


def prompt_for(req):
    return build_prompt(req["brief"], req["context"], req["task"], req.get("task_input"), req.get("reasons"))


def untrusted_refused(trust, platform):
    return trust == "untrusted" and platform == "darwin"


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
        if untrusted_refused(inp["trust"], self.platform):
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
            "prompt": prompt_for(inp),
            "result": "ok",
            "cost": {"usd": 0.0, "seconds": 0.0},
        }
        out.update(reply)
        return {k: v for k, v in out.items() if v is not None}


def _default_runner(argv, stdin, timeout, env, cwd):
    """Run the child in its own process group; on a timeout or any signal kill the whole group."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=env, cwd=cwd, start_new_session=True)
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
    except BaseException:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
        raise
    return proc.returncode, out, err


def child_env(environ, role):
    """The model child's environment: allow-listed names only, and ORG_PARENT_ROLE for its own launches."""
    extra = [n for n in (environ.get("ORG_CHILD_ENV_ALLOW") or "").split(",") if ENV_NAME.match(n)]
    allowed = {n for n in (*CHILD_ENV_ALLOW, *extra) if not n.startswith("ORG_")}
    env = {k: v for k, v in environ.items() if k in allowed}
    env["ORG_PARENT_ROLE"] = role
    return env


def _num(v):
    try:
        return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
    except OverflowError:
        return False


class ClaudeCodeAdapter(_Adapter):
    """Runs `claude -p` once per call: no resumed session, the prompt on stdin, tools by allow-list."""

    def __init__(self, runner=None, claude_bin="claude", platform=None, environ=None):
        super().__init__(platform)
        self.runner = runner or _default_runner
        self.claude_bin = claude_bin
        self.environ = os.environ if environ is None else environ

    def call(self, op, inp):
        self._accept(op, inp)
        argv = [self.claude_bin, "-p", "--output-format", "json", "--no-session-persistence", *ISOLATION_FLAGS]
        argv += ["--allowedTools", ",".join(inp["tools"])] if inp["tools"] else ["--tools", ""]
        prompt = prompt_for(inp)
        try:
            with tempfile.TemporaryDirectory(prefix="agent-run-") as cwd:
                rc, stdout, stderr = self.runner(argv, prompt, inp.get("timeout_seconds", DEFAULT_TIMEOUT),
                                                 child_env(self.environ, inp["role"]), cwd)
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


def t_task_input(c):
    ti = json.dumps({"spec": "INPUT-MARKER-9054"})
    reasons = [{"gate": "spec-gate", "reason": "REASON-MARKER-5513"}]
    out = c.call("run", _req(task_input=ti, reasons=reasons))
    assert "INPUT-MARKER-9054" in out["prompt"] and "REASON-MARKER-5513" in out["prompt"], \
        "task input or reasons missing from the model input"
    task = {"run": "conformance", "task": "review"}
    assert out["prompt"] == build_prompt("Review the change.", [], task, ti, reasons), \
        "model input holds more or less than the brief, task, input and reasons"
    bare = c.call("run", _req())
    assert "INPUT-MARKER-9054" not in bare["prompt"], "task input carried into a call that gave none"


HARNESS_TESTS = {
    "context-only": t_context_only,
    "cost-reported": t_cost_reported,
    "refuses-untrusted-on-macos": t_untrusted,
    "task-input-in-prompt": t_task_input,
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
        self.skipped = {}

    @staticmethod
    def _check(run):
        if not isinstance(run, str) or not RUN_ID.match(run):
            raise PortError("invalid-input", "run id must match [A-Za-z0-9_-]{1,64}")

    def _read(self, run, kind):
        self._check(run)
        self.skipped[(run, kind)] = 0
        if self.dir is None:
            return list(self._mem.get((run, kind), []))
        path = self.dir / f"{run}.{kind}.jsonl"
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except (ValueError, RecursionError):
                self.skipped[(run, kind)] += 1
        return out

    def _add(self, run, kind, entry):
        self._check(run)
        if self.dir is None:
            self._mem.setdefault((run, kind), []).append(entry)
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(entry) + "\n").encode()
        fd = os.open(self.dir / f"{run}.{kind}.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, data)  # one write on an O_APPEND descriptor: concurrent branches cannot interleave
        finally:
            os.close(fd)

    def history(self, run):
        return self._read(run, "history")

    def calls(self, run):
        return self._read(run, "calls")

    def history_skipped(self, run):
        """Corrupt history lines skipped by the last history() read of this run."""
        return self.skipped.get((run, "history"), 0)

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
        return  # the top-level launch: no ORG_PARENT_ROLE
    if parent_role not in roles:
        raise PortError("spawn-refused", f"parent role '{parent_role}' is not in the manifest")
    entry = roles[parent_role]
    if not isinstance(entry, dict):
        raise PortError("bad-manifest", f"roles.{parent_role} must be a map")
    allowed = entry.get("may-spawn", [])
    if not isinstance(allowed, list) or not all(isinstance(a, str) for a in allowed):
        raise PortError("bad-manifest", f"roles.{parent_role}.may-spawn must be a list of strings")
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
    if out["prompt"] != prompt_for(req):
        return "harness-error", "model input differs from brief, context, task, input and reasons"
    if rubric and "verdict" not in out:
        return "invalid-verdict", "judge returned no pass or fail verdict"
    return None, ""


class ScriptedInstances:
    """In-memory instance tool for tests and for ORG_INSTANCES=scripted: grants what is asked, records it."""

    def __init__(self):
        self.acquired, self.released = [], []

    def call(self, op, inp):
        if op == "acquire":
            bad = check_schema(inp, _instances_schema())
            if bad:
                raise PortError("invalid-input", bad[0])
            self.acquired.append(json.loads(json.dumps(inp)))
            return {"instance_id": f"inst-{len(self.acquired)}", "granted": json.loads(json.dumps(inp))}
        if op == "release":
            self.released.append(inp["instance_id"])
            return {"released": True}
        raise PortError("invalid-input", f"unknown operation {op!r}")


def _instances_schema():
    path = CONTRACT_PATH.parent.parent / "contracts" / "instances.json"
    return json.loads(path.read_text())["operations"]["acquire"]["input"]


def _resolve_network(network, instances, policies):
    if instances is None or policies is None:
        raise PortError("network-refused", "a network policy needs an instance tool and a policy table")
    if network not in policies:
        raise PortError("network-refused", f"unknown network policy '{network}'")
    return policies[network]


def _acquire(instances, request):
    """Ask the instance tool for the request. The grant must equal it; a mismatch is released and refused."""
    got = instances.call("acquire", request)
    iid = got.get("instance_id") if isinstance(got, dict) else None
    if not isinstance(iid, str) or not iid:
        raise PortError("network-refused", "instance tool granted no instance_id")
    if got.get("granted") != request:
        try:
            instances.call("release", {"instance_id": iid})
        except Exception:  # noqa: BLE001
            pass
        raise PortError("network-refused", "instance tool granted something other than the request")
    return iid


def run_agent(adapter, store, *, role, brief, task, isolated, trust="trusted", tools=(), manifest=None,
              parent_role=None, signer=None, rubric=False, clock=time.monotonic, timeout_seconds=None,
              task_input=None, reasons=None, network=None, instances=None, network_policies=None):
    """Run one agent call and return the outcome. Raises PortError on a refusal or a failure.

    `isolated` gives the adapter an empty context. Otherwise it gets the earlier results of the same run.
    `task_input` (any JSON value) and `reasons` (gate key to reason) reach the model input. `network` names
    a policy: it is requested from the instance tool and never reaches the adapter. Nothing here enforces it.
    """
    _check_role(role, manifest, parent_role)
    run = task["run"]
    if rubric and "item" not in task:
        raise PortError("invalid-input", "a rubric call needs an item index")
    context = [] if isolated else store.history(run)
    skipped = 0 if isolated else store.history_skipped(run)
    req = {"role": role, "brief": brief, "tools": list(tools), "isolated": bool(isolated), "trust": trust,
           "context": context, "task": dict(task)}
    if timeout_seconds is not None:
        req["timeout_seconds"] = timeout_seconds
    if task_input is not None:
        req["task_input"] = json.dumps(task_input, sort_keys=True)
    if reasons:
        req["reasons"] = [{"gate": k, "reason": v} for k, v in sorted(reasons.items())]
    wanted = _resolve_network(network, instances, network_policies) if network else None
    started = clock()
    out, code, message, instance_id, invoked, release_error = None, None, "", None, False, None
    try:
        if untrusted_refused(trust, getattr(adapter, "platform", sys.platform)):
            raise PortError("refused-untrusted", "untrusted work is not run on macOS")  # before any acquire
        if network:
            instance_id = _acquire(instances, {"isolation": "process", "network": wanted, "trust": trust,
                                               "lifetime_seconds": timeout_seconds or DEFAULT_TIMEOUT})
        invoked = True
        out = adapter.call("run", req)
    except Terminated:
        code, message = "terminated", "terminated by signal"
    except PortError as e:
        code, message = e.code, str(e)
    except Exception as e:  # noqa: BLE001
        code, message = "harness-error", f"{type(e).__name__}: {e}"
    finally:
        if instance_id is not None:
            try:
                instances.call("release", {"instance_id": instance_id})
            except BaseException as e:  # noqa: BLE001
                release_error = f"{type(e).__name__}: {e}"
    seconds = clock() - started
    if code is None:
        code, message = _judge_output(out, req, rubric)
    event = signature = None
    if code is None:
        data = {"run": run, "task": task["task"], "role": role, "result": out["result"]}
        if rubric:
            data = {"run": run, "task": task["task"], "item": task["item"], "role": role,
                    "verdict": out["verdict"], "result": out["result"]}
        event = {"type": "org.rubric-verdict" if rubric else "org.agent-result", "data": data}
        if signer is not None:
            try:
                signature = signer(json.loads(json.dumps(event)))
                if not isinstance(signature, str):
                    raise TypeError("signer did not return a string")
            except Exception as e:  # noqa: BLE001
                code, message = "signer-error", f"{type(e).__name__}: {e}"
    spent = isinstance(out, dict) and _cost_ok(out.get("cost"))
    # usd is unknown when the model may have run and reported no usable cost; a call that never reached it cost 0.
    record = {"run": run, "task": task["task"], "role": role, "isolated": bool(isolated), "ok": code is None,
              "seconds": seconds, "usd": out["cost"]["usd"] if spent else (None if invoked else 0),
              "usd_known": bool(spent or not invoked)}
    if network:
        record.update({"network": network, "instance_id": instance_id, "enforced": False})
    if release_error:
        record["release_error"] = release_error
    if skipped:
        record["history_skipped"] = skipped
    if code is not None:
        record["error"] = code
    store.add_call(run, record)
    if code is not None:
        raise PortError(code, message)
    store.add_history(run, {"role": role, "text": out["result"]})
    if signature is not None:
        event["signature"] = signature
    evidence = [{"name": "prompt", "sha256": _sha(out["prompt"])}, {"name": "result", "sha256": _sha(out["result"])}]
    return {"event": event, "evidence": evidence, "cost": {**out["cost"], "seconds": seconds}}


# ------------------------------------------------------------------ command line


class _BadArguments(Exception):
    pass


DOTTED = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)+$")
MAX_INPUT_BYTES = 1_000_000
MAX_BRIEF_BYTES = 1_000_000


def _parse_args(argv):
    seen, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a == "--isolated":
            if "isolated" in seen:
                raise _BadArguments("--isolated given more than once")
            seen["isolated"] = True
            i += 1
        elif a in ("--role", "--brief", "--input", "--network"):
            key = a[2:]
            if key in seen:
                raise _BadArguments(f"{a} given more than once")
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise _BadArguments(f"{a} needs a value")
            if key == "network" and not DOTTED.match(argv[i + 1]):
                raise _BadArguments("--network must be a dotted policy name like research.source-allowlist")
            seen[key] = argv[i + 1]
            i += 2
        else:
            raise _BadArguments(f"'{a}' is not allowed (allowed: --isolated, --role, --brief, --input, --network)")
    for key in ("role", "brief"):
        if key not in seen:
            raise _BadArguments(f"--{key} is required")
    return seen["role"], seen["brief"], bool(seen.get("isolated")), seen.get("input"), seen.get("network")


def _fd_path(fd):
    """The path an open descriptor really points at, or None when the platform cannot say."""
    getpath = getattr(fcntl, "F_GETPATH", None)
    try:
        if getpath is not None:
            return os.path.realpath(fcntl.fcntl(fd, getpath, b"\0" * 1024).split(b"\0", 1)[0].decode())
        return os.path.realpath(os.readlink(f"/proc/self/fd/{fd}"))
    except (OSError, ValueError):
        return None


def _inside(real, base):
    base = os.path.realpath(base)
    return os.path.commonpath([base, real]) == base


def _read_file_under(path, bases, limit, refuse):
    """Read a regular file through one descriptor: never a symlink, and its real path inside a base.

    `refuse(message)` builds the PortError. Opening and checking use the same descriptor, so there is no
    gap between the check and the read.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as e:
        raise refuse(f"cannot open {os.path.basename(path)}: {e.strerror}") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise refuse("not a regular file")
        real = _fd_path(fd)
        if real is None or not any(_inside(real, b) for b in bases):
            raise refuse("file is outside its allowed directory")
        with os.fdopen(os.dup(fd), "rb") as f:
            data = f.read(limit + 1)
    finally:
        os.close(fd)
    if len(data) > limit:
        raise refuse(f"file is over {limit} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise refuse("file is not UTF-8") from None


def _read_brief(root, rel):
    if not (relative_path_ok(rel, "briefs/", ".md") or relative_path_ok(rel, "criteria/", ".md")):
        raise PortError("brief-refused", "brief must be a relative path under briefs/ or criteria/ ending .md")
    return _read_file_under(os.path.join(root, rel), [root], MAX_BRIEF_BYTES,
                            lambda m: PortError("brief-refused", f"{rel}: {m}"))


def _read_input(path, bases, run, key):
    """Read the runtime-owned task input file. It must sit inside the session directory."""
    text = _read_file_under(path, bases, MAX_INPUT_BYTES, lambda m: PortError("input-refused", m))
    try:
        _check_json_nesting("input file", text)  # a text cap: the same answer on every interpreter and stack
        doc = json.loads(text)
    except LoadError as e:
        raise PortError("input-refused", f"input file: {e.msg}") from None
    except (ValueError, RecursionError):
        raise PortError("input-refused", "input file cannot be read as JSON") from None
    if not isinstance(doc, dict) or set(doc) != {"run", "key", "input", "reasons"}:
        raise PortError("input-refused", "input file must hold exactly run, key, input and reasons")
    reasons = doc["reasons"]
    if not isinstance(reasons, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in reasons.items()):
        raise PortError("input-refused", "input file reasons must map a gate key to a reason string")
    if doc["run"] != run or doc["key"] != key:
        raise PortError("input-refused", "input file run or key does not match ORG_RUN or ORG_KEY")
    return doc["input"], reasons


def _load_manifest(root):
    for name in ("manifest.json", "manifest.yaml", "manifest.yml"):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                return load_document(path)
            except Exception as e:  # noqa: BLE001
                raise PortError("invalid-input", f"cannot load {name}: {e}") from None
    raise PortError("invalid-input", "no manifest in the org root")


def _test_flag(env):
    return env.get("ORG_TEST_HARNESS") == "1"


def _make_adapter(env):
    name = env.get("ORG_HARNESS", "claude-code")
    if name == "claude-code":
        return ClaudeCodeAdapter(environ=env)
    if name == "scripted" and _test_flag(env):
        path = env.get("ORG_HARNESS_SCRIPT")
        try:
            script = json.loads(Path(path).read_text()) if path else None
        except (OSError, ValueError):
            raise PortError("harness-unavailable", "cannot read ORG_HARNESS_SCRIPT") from None
        return ScriptedAdapter(script=script)
    raise PortError("bad-harness", f"unknown harness '{name}'")


def _make_instances(env):
    name = env.get("ORG_INSTANCES")
    if name == "scripted" and _test_flag(env):
        return ScriptedInstances()
    if name is None:
        return None
    raise PortError("network-refused", f"unknown instance tool '{name}'")


def _load_policies(env):
    path = env.get("ORG_NETWORK_POLICIES")
    if not path:
        return None
    try:
        table = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise PortError("network-refused", "cannot read ORG_NETWORK_POLICIES") from None
    if not isinstance(table, dict):
        raise PortError("network-refused", "ORG_NETWORK_POLICIES must hold a map of policy names")
    return table


def _on_sigterm(signum, frame):
    raise Terminated()


def _session_dir(env):
    session = env.get("ORG_SESSION_DIR")
    if not session:
        raise PortError("no-record-dir", "ORG_SESSION_DIR is not set; every call must be recorded")
    if _inside(os.path.realpath(session), env["ORG_ROOT"]):
        raise PortError("no-record-dir", "ORG_SESSION_DIR must be outside ORG_ROOT")
    return session


def _run(role, brief_path, isolated, input_path, network, env):
    for name in ("ORG_ROOT", "ORG_RUN", "ORG_KEY"):
        if not env.get(name):
            raise PortError("invalid-input", f"{name} is not set")
    session = _session_dir(env)
    root = env["ORG_ROOT"]
    trust = env.get("ORG_TRUST", "trusted")
    if trust not in ("trusted", "untrusted"):
        raise PortError("invalid-input", "ORG_TRUST must be trusted or untrusted")
    brief = _read_brief(root, brief_path)
    rubric = brief_path.startswith("criteria/")
    task = {"run": env["ORG_RUN"], "task": env["ORG_KEY"]}
    task_input, reasons = None, None
    if input_path is not None:
        task_input, reasons = _read_input(input_path, [session], task["run"], task["task"])
    if rubric:
        item = env.get("ORG_ITEM", "")
        from_file = task_input.get("item") if isinstance(task_input, dict) else None
        if isinstance(from_file, int) and not isinstance(from_file, bool) and from_file >= 0:
            if item and item != str(from_file):
                raise PortError("invalid-input", "ORG_ITEM differs from the item in the input file")
            item = str(from_file)
        if not (item.isascii() and item.isdigit()):
            raise PortError("invalid-input", "a rubric brief needs the item index (input file or ORG_ITEM)")
        task["item"] = int(item)
    adapter = _make_adapter(env)
    return run_agent(
        adapter, SessionStore(session), role=role, brief=brief, task=task, isolated=isolated, trust=trust,
        manifest=_load_manifest(root), parent_role=env.get("ORG_PARENT_ROLE"), rubric=rubric,
        task_input=task_input, reasons=reasons, network=network,
        instances=_make_instances(env) if network else None,
        network_policies=_load_policies(env) if network else None)


def main(argv, env=None, stdout=None, stderr=None):
    env = os.environ if env is None else env
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    try:
        role, brief_path, isolated, input_path, network = _parse_args(list(argv))
    except _BadArguments as e:
        print(f"agent-run: bad-arguments: {e}", file=stderr)
        return 2
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        outcome = _run(role, brief_path, isolated, input_path, network, env)
    except Terminated:
        print("agent-run: terminated: terminated by signal", file=stderr)
        return 143
    except PortError as e:
        print(f"agent-run: {e}", file=stderr)
        return 143 if e.code == "terminated" else 1
    except Exception as e:  # noqa: BLE001
        print(f"agent-run: internal-error: {type(e).__name__}: {e}", file=stderr)
        return 1
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
    print(json.dumps(outcome), file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
