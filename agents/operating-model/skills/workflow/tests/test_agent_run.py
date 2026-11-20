"""Acceptance tests for the harness adapter contract and agent-run (unit U12).

Every model call here goes through a scripted fake. No test starts a real model.
"""
import hashlib
import io
import json
import math
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

import agent_run as ar  # noqa: E402
from op_conformance import PortError, check_schema  # noqa: E402

CONTRACT_PATH = SKILL / "contracts" / "harness.json"
MARKER = "AUTHOR-SECRET-7731"
RUN = "a" * 32
ROLES = {
    "lead": {"escalates-to": "owner", "may-spawn": ["reviewer", "worker"]},
    "worker": {"escalates-to": "lead"},
    "reviewer": {"escalates-to": "lead"},
    "tester": {"escalates-to": "lead"},
}
MANIFEST = {"owner": "teebor", "roles": ROLES}


def contract():
    return json.loads(CONTRACT_PATH.read_text())


def request(**over):
    base = {
        "role": "reviewer",
        "brief": "Review the change.",
        "tools": [],
        "isolated": False,
        "trust": "trusted",
        "context": [],
        "task": {"run": RUN, "task": "review"},
    }
    base.update(over)
    return base


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Clock:
    """Advances 2.5 seconds per reading, so a call lasts exactly 2.5 seconds."""

    def __init__(self):
        self.now = 100.0

    def __call__(self):
        self.now += 2.5
        return self.now


# ---------------------------------------------------------------- fake claude runner


class FakeRunner:
    def __init__(self, result="done", cost=0.0123, rc=0, raw=None, error=None):
        self.calls = []
        self.result, self.cost, self.rc, self.raw, self.error = result, cost, rc, raw, error

    def __call__(self, argv, stdin, timeout):
        self.calls.append({"argv": list(argv), "stdin": stdin, "timeout": timeout})
        if self.error:
            raise self.error
        if self.raw is not None:
            return self.rc, self.raw, ""
        body = {
            "type": "result",
            "result": self.result,
            "duration_ms": 1500,
            "usage": {"input_tokens": 11, "output_tokens": 7},
        }
        if self.cost is not None:
            body["total_cost_usd"] = self.cost
        return self.rc, json.dumps(body), "boom" if self.rc else ""


def claude(runner=None, platform="linux"):
    return ar.ClaudeCodeAdapter(runner=runner or FakeRunner(), platform=platform)


# ---------------------------------------------------------------- 1. the contract


def test_contract_is_valid():
    assert ar.validate_harness_contract(contract()) == []


def test_contract_states_inputs_outputs_and_errors():
    c = contract()
    props = c["operations"]["run"]["input"]["properties"]
    for key in ("role", "brief", "tools", "isolated"):
        assert key in props
    out = c["outcome"]["properties"]
    for key in ("event", "evidence", "cost"):
        assert key in out
    errors = c["operations"]["run"]["errors"]
    for code in ("invalid-input", "refused-untrusted", "timeout", "harness-unavailable"):
        assert code in errors
    assert "no-metric" in c["program_errors"]


def test_instance_request_keys_are_not_in_the_harness_input():
    props = contract()["operations"]["run"]["input"]["properties"]
    assert "network" not in props and "lifetime_seconds" not in props


def test_committed_contract_holds_no_local_paths():
    text = CONTRACT_PATH.read_text()
    for needle in ("claude" + "-501", "/Us" + "ers/", "~/" + "Fun", "/private" + "/tmp"):
        assert needle not in text


def test_validator_refuses_a_missing_part():
    c = contract()
    del c["operations"]["run"]["guarantees"]
    assert any("missing part: guarantees" in e for e in ar.validate_harness_contract(c))


def test_validator_refuses_a_missing_guarantee():
    c = contract()
    c["operations"]["run"]["guarantees"] = ["cost-reported"]
    errs = ar.validate_harness_contract(c)
    assert any("context-only" in e and "required" in e for e in errs)


def test_validator_refuses_an_untestable_guarantee():
    c = contract()
    c["operations"]["run"]["guarantees"].append("is-clever")
    assert any("is-clever" in e and "no conformance test" in e for e in ar.validate_harness_contract(c))


def test_validator_refuses_a_missing_outcome():
    c = contract()
    del c["outcome"]
    assert any("outcome" in e for e in ar.validate_harness_contract(c))


def test_validator_never_raises_on_junk():
    for junk in (None, [], {"port": "Harness"}, {"port": "Harness", "operations": 3}):
        assert ar.validate_harness_contract(junk)


# ---------------------------------------------------------------- 2. conformance


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_scripted_adapter_passes_conformance(platform):
    adapter = ar.ScriptedAdapter(platform=platform)
    assert ar.run_harness_conformance(contract(), adapter, platform=platform) == []


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_claude_code_adapter_passes_conformance(platform):
    adapter = claude(platform=platform)
    assert ar.run_harness_conformance(contract(), adapter, platform=platform) == []


def test_conformance_refuses_a_refused_contract():
    c = contract()
    del c["operations"]["run"]["guarantees"]
    fails = ar.run_harness_conformance(c, ar.ScriptedAdapter())
    assert fails and all(f.startswith("contract: refused:") for f in fails)


class LeakyAdapter(ar.ScriptedAdapter):
    """Remembers earlier context and replays it into an isolated call."""

    memory = ""

    def call(self, op, inp):
        ctx = list(inp.get("context", []))
        if inp.get("isolated") and self.memory:
            inp = {**inp, "context": ctx + [{"role": "leak", "text": self.memory}], "isolated": False}
        out = super().call(op, inp)
        self.memory = " ".join(c["text"] for c in ctx) or self.memory
        return out


class ContextFromNowhere(ar.ScriptedAdapter):
    def call(self, op, inp):
        out = super().call(op, inp)
        return {**out, "prompt": out["prompt"] + "\nprevious session: " + MARKER}


class NoCostAdapter(ar.ScriptedAdapter):
    def call(self, op, inp):
        out = super().call(op, inp)
        out.pop("cost", None)
        return out


class AcceptsUntrusted(ar.ScriptedAdapter):
    def call(self, op, inp):
        return super().call(op, {**inp, "trust": "trusted"})


class AcceptsAnything(ar.ScriptedAdapter):
    def call(self, op, inp):
        return super().call(op, {k: v for k, v in inp.items() if k in request()})


class IsolatedWithContext(ar.ScriptedAdapter):
    def call(self, op, inp):
        return super().call(op, {**inp, "isolated": False})


def _fails(adapter, platform="darwin"):
    return ar.run_harness_conformance(contract(), adapter, platform=platform)


def test_conformance_catches_context_leaking_into_an_isolated_call():
    assert any("context-only" in f for f in _fails(LeakyAdapter(platform="darwin")))


def test_conformance_catches_context_the_caller_never_gave():
    assert any("context-only" in f for f in _fails(ContextFromNowhere(platform="darwin")))


def test_conformance_catches_a_missing_cost():
    assert any("cost" in f for f in _fails(NoCostAdapter(platform="darwin")))


def test_conformance_catches_untrusted_work_accepted_on_macos():
    fails = _fails(AcceptsUntrusted(platform="darwin"))
    assert any("refuses-untrusted-on-macos" in f for f in fails)


def test_conformance_catches_isolated_with_context_accepted():
    assert any("context-only" in f for f in _fails(IsolatedWithContext(platform="darwin")))


def test_conformance_catches_extra_keys_accepted():
    assert any("invalid-input" in f for f in _fails(AcceptsAnything(platform="darwin")))


# ---------------------------------------------------------------- 3. [A] --isolated


def _author_then_reviewer(adapter, isolated, store=None):
    store = store or ar.SessionStore()
    ar.run_agent(adapter, store, role="worker", brief="Write the code.", task={"run": RUN, "task": "build"},
                 isolated=False, manifest=MANIFEST)
    return ar.run_agent(adapter, store, role="reviewer", brief="Review the change.",
                        task={"run": RUN, "task": "review"}, isolated=isolated, manifest=MANIFEST)


class Recording(ar.ScriptedAdapter):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.seen = []

    def call(self, op, inp):
        self.seen.append(inp)
        return super().call(op, inp)


def _author_marker_adapter():
    return Recording(script=[{"result": f"I wrote it. {MARKER}"}, {"result": "looks fine"}])


def test_isolated_reviewer_input_has_no_author_marker():
    adapter = _author_marker_adapter()
    _author_then_reviewer(adapter, isolated=True)
    reviewer = adapter.seen[1]
    assert reviewer["context"] == [] and reviewer["isolated"] is True
    assert MARKER not in json.dumps(reviewer)


def test_isolated_reviewer_prompt_has_no_author_marker():
    adapter = _author_marker_adapter()
    _author_then_reviewer(adapter, isolated=True)
    prompt = ar.build_prompt(adapter.seen[1]["brief"], adapter.seen[1]["context"], adapter.seen[1]["task"])
    assert MARKER not in prompt


def test_control_shared_reviewer_input_does_carry_the_marker():
    # Without --isolated the same marker must arrive, or the isolated test proves nothing.
    adapter = _author_marker_adapter()
    _author_then_reviewer(adapter, isolated=False)
    assert MARKER in json.dumps(adapter.seen[1])


def test_isolated_reviewer_through_claude_adapter_has_no_marker_in_argv_or_stdin():
    runner = FakeRunner(result=f"wrote {MARKER}")
    adapter = claude(runner)
    _author_then_reviewer(adapter, isolated=True)
    reviewer_call = runner.calls[1]
    assert MARKER not in json.dumps(reviewer_call["argv"]) and MARKER not in reviewer_call["stdin"]


def test_shared_reviewer_through_claude_adapter_carries_the_marker():
    runner = FakeRunner(result=f"wrote {MARKER}")
    _author_then_reviewer(claude(runner), isolated=False)
    assert MARKER in runner.calls[1]["stdin"]


def test_a_run_never_sees_another_runs_history():
    store = ar.SessionStore()
    adapter = _author_marker_adapter()
    ar.run_agent(adapter, store, role="worker", brief="b", task={"run": RUN, "task": "build"}, isolated=False,
                 manifest=MANIFEST)
    ar.run_agent(adapter, store, role="reviewer", brief="b", task={"run": "b" * 32, "task": "review"},
                 isolated=False, manifest=MANIFEST)
    assert adapter.seen[1]["context"] == []


# ---------------------------------------------------------------- 4. [A] cost and time


def test_cost_and_time_are_recorded_for_a_call():
    store = ar.SessionStore()
    out = ar.run_agent(claude(), store, role="worker", brief="b", task={"run": RUN, "task": "build"},
                       isolated=True, manifest=MANIFEST, clock=Clock())
    assert out["cost"]["usd"] == pytest.approx(0.0123)
    assert out["cost"]["seconds"] == pytest.approx(2.5)
    assert out["cost"]["input_tokens"] == 11 and out["cost"]["output_tokens"] == 7
    [rec] = store.calls(RUN)
    assert rec["ok"] is True and rec["usd"] == pytest.approx(0.0123) and rec["seconds"] == pytest.approx(2.5)
    assert rec["role"] == "worker" and rec["task"] == "build"


def test_a_call_with_no_metric_is_refused():
    store = ar.SessionStore()
    with pytest.raises(PortError) as e:
        ar.run_agent(claude(FakeRunner(cost=None)), store, role="worker", brief="b",
                     task={"run": RUN, "task": "build"}, isolated=True, manifest=MANIFEST)
    assert e.value.code == "no-metric"


def test_a_refused_call_is_still_recorded_and_leaves_no_session_history():
    store = ar.SessionStore()
    with pytest.raises(PortError):
        ar.run_agent(claude(FakeRunner(cost=None)), store, role="worker", brief="b",
                     task={"run": RUN, "task": "build"}, isolated=True, manifest=MANIFEST, clock=Clock())
    [rec] = store.calls(RUN)
    assert rec["ok"] is False and rec["error"] == "no-metric" and rec["seconds"] == pytest.approx(2.5)
    assert store.history(RUN) == []


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, "free", True, None])
def test_an_unusable_cost_value_is_refused(bad):
    class Bad(ar.ScriptedAdapter):
        def call(self, op, inp):
            out = super().call(op, inp)
            out["cost"] = {"usd": bad, "seconds": 1.0}
            return out

    with pytest.raises(PortError) as e:
        ar.run_agent(Bad(), ar.SessionStore(), role="worker", brief="b", task={"run": RUN, "task": "x"},
                     isolated=True, manifest=MANIFEST)
    assert e.value.code == "no-metric"


def test_a_failed_harness_call_records_time_and_the_error_code():
    store = ar.SessionStore()
    with pytest.raises(PortError) as e:
        ar.run_agent(claude(FakeRunner(error=FileNotFoundError("claude"))), store, role="worker", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST, clock=Clock())
    assert e.value.code == "harness-unavailable"
    [rec] = store.calls(RUN)
    assert rec["error"] == "harness-unavailable" and rec["seconds"] == pytest.approx(2.5)


def test_every_call_is_recorded_in_order():
    store = ar.SessionStore()
    adapter = Recording(script=[{"result": "1"}, {"result": "2"}, {"result": "3"}])
    for n in range(3):
        ar.run_agent(adapter, store, role="worker", brief="b", task={"run": RUN, "task": f"t{n}"},
                     isolated=True, manifest=MANIFEST)
    assert [r["task"] for r in store.calls(RUN)] == ["t0", "t1", "t2"]


def test_file_store_persists_calls_and_history(tmp_path):
    store = ar.SessionStore(tmp_path)
    ar.run_agent(Recording(script=[{"result": "kept"}]), store, role="worker", brief="b",
                 task={"run": RUN, "task": "build"}, isolated=True, manifest=MANIFEST)
    again = ar.SessionStore(tmp_path)
    assert again.history(RUN) == [{"role": "worker", "text": "kept"}]
    assert len(again.calls(RUN)) == 1


def test_store_refuses_an_unsafe_run_id(tmp_path):
    store = ar.SessionStore(tmp_path)
    for bad in ("../x", "a/b", "", "x" * 65, "a b"):
        with pytest.raises(PortError) as e:
            store.history(bad)
        assert e.value.code == "invalid-input"


# ---------------------------------------------------------------- run_agent: role, spawn, trust, outcome


def test_owner_role_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="owner", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST)
    assert e.value.code == "role-refused"


def test_a_role_missing_from_the_manifest_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="ghost", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST)
    assert e.value.code == "role-refused"


def test_spawn_the_may_spawn_list_does_not_allow_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="tester", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST, parent_role="lead")
    assert e.value.code == "spawn-refused"


def test_spawn_a_role_with_no_may_spawn_entry_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="reviewer", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST, parent_role="worker")
    assert e.value.code == "spawn-refused"


def test_spawn_the_list_allows_goes_through():
    out = ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="reviewer", brief="b",
                       task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST, parent_role="lead")
    assert out["event"]["data"]["role"] == "reviewer"


def test_an_unknown_parent_role_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="reviewer", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST, parent_role="ghost")
    assert e.value.code == "spawn-refused"


def test_untrusted_work_is_refused_on_macos_and_recorded():
    store = ar.SessionStore()
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(platform="darwin"), store, role="worker", brief="b",
                     task={"run": RUN, "task": "x"}, isolated=True, trust="untrusted", manifest=MANIFEST)
    assert e.value.code == "refused-untrusted"
    assert store.calls(RUN)[0]["error"] == "refused-untrusted"


def test_untrusted_work_is_not_refused_off_macos():
    out = ar.run_agent(ar.ScriptedAdapter(platform="linux"), ar.SessionStore(), role="worker", brief="b",
                       task={"run": RUN, "task": "x"}, isolated=True, trust="untrusted", manifest=MANIFEST)
    assert out["event"]["type"] == "org.agent-result"


def test_outcome_matches_the_contract_and_hashes_the_evidence():
    adapter = Recording(script=[{"result": "all good"}])
    out = ar.run_agent(adapter, ar.SessionStore(), role="worker", brief="Do it.",
                       task={"run": RUN, "task": "build"}, isolated=True, manifest=MANIFEST)
    assert check_schema(out, contract()["outcome"]) == []
    assert out["event"]["type"] == "org.agent-result"
    assert out["event"]["data"] == {"run": RUN, "task": "build", "role": "worker", "result": "all good"}
    prompt = ar.build_prompt("Do it.", [], {"run": RUN, "task": "build"})
    assert {e["name"]: e["sha256"] for e in out["evidence"]} == {"prompt": sha(prompt), "result": sha("all good")}
    assert "signature" not in out["event"]


def test_a_signer_adds_a_signature_over_the_event():
    seen = []

    def signer(event):
        seen.append(json.dumps(event, sort_keys=True))
        return "sig-1"

    out = ar.run_agent(ar.ScriptedAdapter(), ar.SessionStore(), role="worker", brief="b",
                       task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST, signer=signer)
    assert out["event"]["signature"] == "sig-1"
    assert "signature" not in json.loads(seen[0])


def test_rubric_call_returns_an_org_rubric_verdict():
    adapter = Recording(script=[{"result": "criterion met", "verdict": "pass"}])
    out = ar.run_agent(adapter, ar.SessionStore(), role="reviewer", brief="Judge it.",
                       task={"run": RUN, "task": "review", "item": 2}, isolated=True, manifest=MANIFEST,
                       rubric=True)
    assert out["event"]["type"] == "org.rubric-verdict"
    assert out["event"]["data"] == {
        "run": RUN, "task": "review", "item": 2, "role": "reviewer", "verdict": "pass", "result": "criterion met"}
    assert check_schema(out, contract()["outcome"]) == []


def test_rubric_call_with_no_verdict_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(script=[{"result": "hm"}]), ar.SessionStore(), role="reviewer", brief="b",
                     task={"run": RUN, "task": "review", "item": 0}, isolated=True, manifest=MANIFEST,
                     rubric=True)
    assert e.value.code == "invalid-verdict"


def test_rubric_call_without_an_item_index_is_refused():
    with pytest.raises(PortError) as e:
        ar.run_agent(ar.ScriptedAdapter(script=[{"result": "x", "verdict": "pass"}]), ar.SessionStore(),
                     role="reviewer", brief="b", task={"run": RUN, "task": "review"}, isolated=True,
                     manifest=MANIFEST, rubric=True)
    assert e.value.code == "invalid-input"


def test_non_rubric_call_does_not_return_a_verdict_event():
    out = ar.run_agent(ar.ScriptedAdapter(script=[{"result": "x", "verdict": "pass"}]), ar.SessionStore(),
                       role="worker", brief="b", task={"run": RUN, "task": "x"}, isolated=True, manifest=MANIFEST)
    assert out["event"]["type"] == "org.agent-result" and "verdict" not in out["event"]["data"]


def test_adapter_output_that_breaks_the_contract_is_refused():
    class Garbage(ar.ScriptedAdapter):
        def call(self, op, inp):
            return {"prompt": 1, "cost": {"usd": 0, "seconds": 0}}

    with pytest.raises(PortError) as e:
        ar.run_agent(Garbage(), ar.SessionStore(), role="worker", brief="b", task={"run": RUN, "task": "x"},
                     isolated=True, manifest=MANIFEST)
    assert e.value.code == "harness-error"


def test_adapter_exception_is_wrapped_as_harness_error():
    class Boom(ar.ScriptedAdapter):
        def call(self, op, inp):
            raise ValueError("kaput")

    store = ar.SessionStore()
    with pytest.raises(PortError) as e:
        ar.run_agent(Boom(), store, role="worker", brief="b", task={"run": RUN, "task": "x"}, isolated=True,
                     manifest=MANIFEST)
    assert e.value.code == "harness-error" and store.calls(RUN)[0]["error"] == "harness-error"


# ---------------------------------------------------------------- the scripted adapter


def test_scripted_adapter_replays_replies_in_order_then_refuses():
    a = ar.ScriptedAdapter(script=[{"result": "one"}, {"result": "two"}])
    assert a.call("run", request())["result"] == "one"
    assert a.call("run", request())["result"] == "two"
    with pytest.raises(PortError) as e:
        a.call("run", request())
    assert e.value.code == "harness-error"


def test_scripted_adapter_rejects_an_unknown_operation():
    with pytest.raises(PortError) as e:
        ar.ScriptedAdapter().call("stop", {})
    assert e.value.code == "invalid-input"


# ---------------------------------------------------------------- the Claude Code adapter


def test_claude_adapter_builds_a_print_mode_call_with_no_resumed_session():
    runner = FakeRunner()
    claude(runner).call("run", request(tools=["Read", "Grep"]))
    argv = runner.calls[0]["argv"]
    assert argv[0] == "claude" and "-p" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "--no-session-persistence" in argv
    for flag in ("--resume", "--continue", "-c", "-r"):
        assert flag not in argv
    assert argv[argv.index("--allowedTools") + 1] == "Read,Grep"


def test_claude_adapter_sends_the_prompt_on_stdin_and_the_timeout():
    runner = FakeRunner()
    ctx = [{"role": "worker", "text": "I did X"}]
    claude(runner).call("run", request(brief="Be brief.", context=ctx, timeout_seconds=30))
    call = runner.calls[0]
    assert "Be brief." in call["stdin"] and "worker: I did X" in call["stdin"]
    assert "Be brief." not in " ".join(call["argv"])
    assert call["timeout"] == 30


def test_claude_adapter_with_no_tools_allows_none():
    runner = FakeRunner()
    claude(runner).call("run", request(tools=[]))
    argv = runner.calls[0]["argv"]
    assert "--allowedTools" not in argv and argv[argv.index("--tools") + 1] == ""


def test_claude_adapter_parses_result_cost_and_tokens():
    out = claude(FakeRunner(result="hello", cost=0.5)).call("run", request())
    assert out["result"] == "hello"
    assert out["cost"] == {"usd": 0.5, "seconds": 1.5, "input_tokens": 11, "output_tokens": 7}
    assert "verdict" not in out


def test_claude_adapter_parses_a_verdict_line():
    out = claude(FakeRunner(result="fine\nVERDICT: PASS")).call("run", request(task={"run": RUN, "task": "r", "item": 0}))
    assert out["verdict"] == "pass"
    out = claude(FakeRunner(result="no\nVERDICT: fail\n")).call("run", request(task={"run": RUN, "task": "r", "item": 0}))
    assert out["verdict"] == "fail"


def test_claude_adapter_ignores_a_verdict_line_that_is_not_the_last():
    out = claude(FakeRunner(result="VERDICT: pass\nbut actually unsure")).call(
        "run", request(task={"run": RUN, "task": "r", "item": 0}))
    assert "verdict" not in out


def test_claude_adapter_omits_cost_when_the_cli_reports_none():
    assert "cost" not in claude(FakeRunner(cost=None)).call("run", request())


@pytest.mark.parametrize("raw", ["not json", "[]", '{"result": 5}', '{"type": "result"}'])
def test_claude_adapter_refuses_unparseable_output(raw):
    with pytest.raises(PortError) as e:
        claude(FakeRunner(raw=raw)).call("run", request())
    assert e.value.code == "harness-error"


def test_claude_adapter_refuses_a_failing_exit_code():
    with pytest.raises(PortError) as e:
        claude(FakeRunner(rc=1)).call("run", request())
    assert e.value.code == "harness-error" and "boom" in str(e.value)


def test_claude_adapter_maps_timeout_and_missing_binary():
    with pytest.raises(PortError) as e:
        claude(FakeRunner(error=subprocess.TimeoutExpired("claude", 3))).call("run", request())
    assert e.value.code == "timeout"
    with pytest.raises(PortError) as e:
        claude(FakeRunner(error=FileNotFoundError("claude"))).call("run", request())
    assert e.value.code == "harness-unavailable"


def test_claude_adapter_refuses_untrusted_work_on_macos_before_any_call():
    runner = FakeRunner()
    with pytest.raises(PortError) as e:
        claude(runner, platform="darwin").call("run", request(trust="untrusted"))
    assert e.value.code == "refused-untrusted" and runner.calls == []


def test_default_runner_runs_a_real_subprocess(tmp_path):
    # A fake `claude` script, not the real binary: no model call.
    script = tmp_path / "fake-claude"
    script.write_text(
        "#!/bin/sh\ncat >/dev/null\n"
        'echo \'{"type":"result","result":"from script","total_cost_usd":0.25,"duration_ms":10}\'\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    out = ar.ClaudeCodeAdapter(claude_bin=str(script), platform="linux").call("run", request())
    assert out["result"] == "from script" and out["cost"]["usd"] == 0.25


def test_default_runner_maps_a_missing_binary_to_unavailable(tmp_path):
    adapter = ar.ClaudeCodeAdapter(claude_bin=str(tmp_path / "nope"), platform="linux")
    with pytest.raises(PortError) as e:
        adapter.call("run", request())
    assert e.value.code == "harness-unavailable"


# ---------------------------------------------------------------- command line


@pytest.fixture
def org(tmp_path):
    root = tmp_path / "org"
    (root / "briefs").mkdir(parents=True)
    (root / "criteria").mkdir()
    (root / "briefs" / "build.md").write_text("Write the code.")
    (root / "briefs" / "review.md").write_text("Review the change.")
    (root / "criteria" / "quality.md").write_text("Is it clear?")
    (root / "manifest.json").write_text(json.dumps(MANIFEST))
    script = tmp_path / "script.json"
    script.write_text(json.dumps([{"result": f"built {MARKER}"}, {"result": "reviewed"}]))
    env = {
        "ORG_ROOT": str(root),
        "ORG_RUN": RUN,
        "ORG_KEY": "build",
        "ORG_SESSION_DIR": str(tmp_path / "sessions"),
        "ORG_HARNESS": "scripted",
        "ORG_HARNESS_SCRIPT": str(script),
    }
    return root, env, tmp_path


def cli(argv, env):
    out, err = io.StringIO(), io.StringIO()
    code = ar.main(list(argv), env=env, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_runs_a_step_and_prints_the_outcome(org):
    root, env, _ = org
    code, out, err = cli(["--role", "worker", "--brief", "briefs/build.md"], env)
    assert code == 0, err
    outcome = json.loads(out)
    assert check_schema(outcome, contract()["outcome"]) == []
    assert outcome["event"]["data"]["role"] == "worker" and outcome["event"]["data"]["task"] == "build"


def test_cli_isolated_reviewer_gets_no_author_context(org):
    root, env, _ = org
    assert cli(["--role", "worker", "--brief", "briefs/build.md"], env)[0] == 0
    code, out, _ = cli(["--isolated", "--role", "reviewer", "--brief", "briefs/review.md"],
                       {**env, "ORG_KEY": "review"})
    assert code == 0
    clean = ar.build_prompt("Review the change.", [], {"run": RUN, "task": "review"})
    assert {e["name"]: e["sha256"] for e in json.loads(out)["evidence"]}["prompt"] == sha(clean)


def test_cli_shared_reviewer_gets_author_context(org):
    root, env, _ = org
    cli(["--role", "worker", "--brief", "briefs/build.md"], env)
    code, out, _ = cli(["--role", "reviewer", "--brief", "briefs/review.md"], {**env, "ORG_KEY": "review"})
    clean = ar.build_prompt("Review the change.", [], {"run": RUN, "task": "review"})
    assert {e["name"]: e["sha256"] for e in json.loads(out)["evidence"]}["prompt"] != sha(clean)


def test_cli_rubric_brief_returns_a_verdict_event(org):
    root, env, tmp = org
    (tmp / "script.json").write_text(json.dumps([{"result": "ok", "verdict": "pass"}]))
    code, out, err = cli(["--role", "reviewer", "--brief", "criteria/quality.md"],
                         {**env, "ORG_KEY": "review", "ORG_ITEM": "1"})
    assert code == 0, err
    event = json.loads(out)["event"]
    assert event["type"] == "org.rubric-verdict" and event["data"]["item"] == 1 and event["data"]["verdict"] == "pass"


def test_cli_rubric_brief_needs_the_item_index(org):
    root, env, _ = org
    code, out, err = cli(["--role", "reviewer", "--brief", "criteria/quality.md"], env)
    assert code == 1 and "invalid-input" in err and out == ""


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--role", "worker"],
        ["--brief", "briefs/build.md"],
        ["--role", "worker", "--brief", "briefs/build.md", "--isolated", "--isolated"],
        ["--role", "worker", "--role", "lead", "--brief", "briefs/build.md"],
        ["--role", "worker", "--brief", "briefs/build.md", "--brief", "briefs/review.md"],
        ["--role", "worker", "--brief", "briefs/build.md", "--verbose"],
        ["--role", "worker", "--brief", "briefs/build.md", "extra"],
        ["--role=worker", "--brief", "briefs/build.md"],
        ["--role", "worker", "--brief", "briefs/build.md", "--env", "X=1"],
        ["--role", "worker", "--brief", "briefs/build.md", "--stdin", "x"],
        ["--role", "worker", "--brief", "briefs/build.md", "--directory", "/"],
        ["--role"],
        ["--role", "--brief", "briefs/build.md"],
    ],
)
def test_cli_refuses_any_argument_but_the_three_flags(org, argv):
    root, env, _ = org
    code, out, err = cli(argv, env)
    assert code == 2 and out == "" and "bad-arguments" in err


def test_cli_refuses_the_owner_role(org):
    root, env, _ = org
    code, out, err = cli(["--role", "owner", "--brief", "briefs/build.md"], env)
    assert code == 1 and "role-refused" in err and out == ""


@pytest.mark.parametrize(
    "brief",
    ["build.md", "/etc/passwd", "briefs/../manifest.json", "briefs/nope.md", "briefs/build.txt", "other/build.md",
     "briefs/", "briefs//build.md", "briefs\\build.md"],
)
def test_cli_refuses_a_brief_that_is_not_a_file_under_briefs_or_criteria(org, brief):
    root, env, _ = org
    code, out, err = cli(["--role", "worker", "--brief", brief], env)
    assert code == 1 and "brief-refused" in err


def test_cli_refuses_a_brief_symlinked_outside_the_root(org):
    root, env, tmp = org
    (tmp / "secret.md").write_text("outside")
    (root / "briefs" / "link.md").symlink_to(tmp / "secret.md")
    code, out, err = cli(["--role", "worker", "--brief", "briefs/link.md"], env)
    assert code == 1 and "brief-refused" in err


def test_cli_refuses_when_the_record_directory_is_not_set(org):
    root, env, _ = org
    env = {k: v for k, v in env.items() if k != "ORG_SESSION_DIR"}
    code, out, err = cli(["--role", "worker", "--brief", "briefs/build.md"], env)
    assert code == 1 and "no-record-dir" in err and out == ""


@pytest.mark.parametrize("name", ["ORG_ROOT", "ORG_RUN", "ORG_KEY"])
def test_cli_refuses_when_a_runtime_variable_is_missing(org, name):
    root, env, _ = org
    env = {k: v for k, v in env.items() if k != name}
    code, out, err = cli(["--role", "worker", "--brief", "briefs/build.md"], env)
    assert code == 1 and name in err


def test_cli_refuses_an_unsafe_run_id(org):
    root, env, _ = org
    code, out, err = cli(["--role", "worker", "--brief", "briefs/build.md"], {**env, "ORG_RUN": "../evil"})
    assert code == 1 and "invalid-input" in err


def test_cli_refuses_an_unknown_harness(org):
    root, env, _ = org
    code, out, err = cli(["--role", "worker", "--brief", "briefs/build.md"], {**env, "ORG_HARNESS": "gpt"})
    assert code == 1 and "harness-unavailable" in err


def test_cli_enforces_the_spawn_list_from_the_parent_role(org):
    root, env, _ = org
    code, out, err = cli(["--role", "tester", "--brief", "briefs/build.md"], {**env, "ORG_PARENT_ROLE": "lead"})
    assert code == 1 and "spawn-refused" in err


def test_cli_missing_cost_exits_one_with_no_metric(org):
    root, env, tmp = org
    (tmp / "script.json").write_text(json.dumps([{"result": "x", "cost": None}]))
    code, out, err = cli(["--role", "worker", "--brief", "briefs/build.md"], env)
    assert code == 1 and "no-metric" in err and out == ""
    assert ar.SessionStore(Path(env["ORG_SESSION_DIR"])).calls(RUN)[0]["error"] == "no-metric"


def test_cli_runs_as_a_program(org):
    root, env, tmp = org
    r = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "agent_run.py"), "--role", "worker", "--brief", "briefs/build.md"],
        capture_output=True, text=True, env={**os.environ, **env},
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["event"]["type"] == "org.agent-result"


def test_no_local_paths_in_the_committed_sources():
    for rel in ("scripts/agent_run.py", "tests/test_agent_run.py"):
        text = (SKILL / rel).read_text()
        for needle in ("claude" + "-501", "/Us" + "ers/", "~/" + "Fun", "/private" + "/tmp"):
            assert needle not in text
