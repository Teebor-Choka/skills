"""Acceptance tests for the org runtime (U13b): ledger, resume, signatures, metrics, rungs, the real-time driver.

All model use is scripted. Tests that need `ssh-keygen` skip with a reason when it is missing; the logic tests use
a fake verifier and always run. The signing helper lives here only: the runtime module has no private-key path.
"""
import ast
import copy
import gc
import json
import os
import shutil
import time
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import interpreter as it  # noqa: E402
import org_runtime as ort  # noqa: E402
import validate_manifest as vm  # noqa: E402
from interpreter import JudgeRequest, ScriptedHost, StepOutcome  # noqa: E402

RID = "0123456789abcdef0123456789abcdef"
ROOT_ID = "test-root"
KEY = b"k" * 32
NS = "org-event"
HAVE_SSH = shutil.which("ssh-keygen") is not None
needs_ssh = pytest.mark.skipif(not HAVE_SSH, reason="ssh-keygen is not installed")

# ---------------------------------------------------------------- a small org root on disk

CATALOG = {"m1": {"scope": "node", "unit": "count", "better": "lower", "formula": "f",
                  "collector": "collectors/m1.py", "reads": ["run-ledger"]}}
COLLECTOR = ("import json, os\n"
             "print(json.dumps(len(open(os.environ['ORG_METRIC_INPUT']).readlines())))\n")
STUB = "import sys\nsys.stderr.write('not implemented')\nsys.exit(3)\n"


def manifest(**over):
    m = {"owner": "teebor", "namespace": "org",
         "roles": {"worker": {"escalates-to": "owner"}, "pm": {"escalates-to": "owner"},
                   "reviewer": {"escalates-to": "owner"}, "improver": {"escalates-to": "owner"}},
         "workflows": {"t": {"path": "workflows/t.json", "floors": []}}, "vetoes": ["v"]}
    if "checks" in getattr(vm, "TOP_KEYS", ()):
        m["checks"] = {"c": "shape"}
    m.update(over)
    return m


def leaf(metrics=("m1",), command="work", role="worker", by="code"):
    return {"run": {"shell": {"command": command, "arguments": []}},
            "metadata": {"org": {"by": by, "role": role, "metrics": list(metrics), "acceptance": [{"check": "c"}]}}}


def gate(signer=None):
    org = {"by": "human", "role": "pm", "metrics": ["m1"], "acceptance": [{"human": "ok"}]}
    if signer:
        org["signer"] = signer
    return {"listen": {"to": {"one": {"with": {"type": "org.owner-decided"}}}}, "timeout": {"after": {"hours": 1}},
            "metadata": {"org": org}}


def doc(*tasks, name="t"):
    return {"document": {"dsl": "1.1.0", "namespace": "org", "name": name, "version": "0.1.0"},
            "do": [{n: t} for n, t in tasks]}


def make_root(tmp, wf=None, man=None, catalog=CATALOG, collector=COLLECTOR):
    root = tmp / "org"
    for d in ("workflows", "collectors", "checks", "briefs", "criteria", "bin"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(man or manifest()))
    (root / "metrics.json").write_text(json.dumps(catalog))
    (root / "workflows" / "t.json").write_text(json.dumps(wf or doc(("a", leaf()), ("b", leaf()), ("c", leaf()))))
    (root / "checks" / "c.py").write_text("import sys\nsys.exit(0)\n")
    (root / "bin" / "work").write_text("#!/bin/sh\nexit 0\n")
    (root / "briefs" / "x.md").write_text("brief")
    (root / "criteria" / "q.md").write_text("Is it clear?")
    if collector is not None:
        (root / "collectors" / "m1.py").write_text(collector)
    return root


class FakeVerifier:
    """A signature is the text `by:<principal>`. No cryptography: the ring logic is under test."""

    def verify(self, principal, keys, payload, sig, namespace):
        return sig == f"by:{principal}" and bool(keys)


def fake_ring(**keys):
    return ort.KeyRing({"owner": ["ssh-ed25519 AAAAowner"], "pm": ["ssh-ed25519 AAAApm"], **keys},
                       verifier=FakeVerifier())


def runtime(tmp, root=None, host=None, ring=None, **kw):
    root = root or make_root(tmp)
    kw.setdefault("snapshots", ort.UNENFORCED)
    kw.setdefault("frozen", ort.NO_OUTSIDE)
    kw.setdefault("allow_run_id", True)
    kw.setdefault("root_id", ROOT_ID)
    kw.setdefault("collector", lambda *a, **k: 0)
    return ort.OrgRuntime(root, ledger_path=tmp / "run.ledger", ledger_key=KEY, ring=ring or fake_ring(),
                          host=host or ScriptedHost(), **kw)


def summary(res):
    return (res.status, res.errors, res.statuses, res.accepted)


def ev(task="a", decision="approve", sig="by:owner", run=RID, id=None, **data):
    out = {"type": "org.owner-decided", "data": {"run": run, "task": task, "decision": decision, **data},
           "signature": sig}
    if id is not False:
        out["id"] = id if id is not None else f"e-{task}-{decision}-{sig}-{run[:4]}"
    return out


# ---------------------------------------------------------------- 1. every event is in the ledger, replay rebuilds state


def test_every_interpreter_event_is_appended_to_the_ledger(tmp_path):
    rt = runtime(tmp_path)
    res = rt.run("t", run_id=RID)
    assert res.status == "success", res.errors
    entries = ort.RunLedger(tmp_path / "run.ledger", KEY).read()
    logged = [e["body"] for e in entries if e["kind"] == "log"]
    assert [b["seq"] for b in logged] == [e["seq"] for e in res.events]
    assert [b["kind"] for b in logged] == [e["kind"] for e in res.events]
    assert entries[0]["kind"] == "header" and entries[0]["body"]["run_id"] == RID


def test_ledger_chain_detects_an_edit_and_a_reorder(tmp_path):
    runtime(tmp_path).run("t", run_id=RID)
    path = tmp_path / "run.ledger"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2], lines[1]] + lines[3:]) + "\n")
    with pytest.raises(ort.LedgerError):
        ort.RunLedger(path, KEY).read()
    path.write_text("\n".join(lines[:1] + [lines[1].replace("run-start", "run-stop")] + lines[2:]) + "\n")
    with pytest.raises(ort.LedgerError):
        ort.RunLedger(path, KEY).read()


def test_replay_rebuilds_the_same_state_with_no_live_call(tmp_path):
    host = ScriptedHost(steps={"b": {"exit_code": 1, "error": "boom"}})
    rt = runtime(tmp_path, host=host)
    live = rt.run("t", run_id=RID)
    assert live.status == "error"
    again = runtime(tmp_path, host=ScriptedHost(steps={"a": {"exit_code": 9}}))  # a live call would change state
    assert summary(again.replay()) == summary(live)


def test_replay_after_a_rework_round_matches(tmp_path):
    loop = {"for": {"in": [1, 2], "each": "n"}, "while": "${ true }", "do": [{"a": leaf()}]}
    wf = doc(("r", loop))
    root = make_root(tmp_path, wf=wf)
    rt = runtime(tmp_path, root=root)
    live = rt.run("t", run_id=RID)
    assert summary(runtime(tmp_path, root=root).replay()) == summary(live)


# ---------------------------------------------------------------- 2. a killed run resumes to the same final state


class Killed(BaseException):
    pass


class KillingHost(ScriptedHost):
    def __init__(self, after, **kw):
        super().__init__(**kw)
        self.after, self.live = after, 0

    def _tick(self):
        self.live += 1
        if self.live > self.after:
            raise Killed()

    def run_step(self, req):
        self._tick()
        return super().run_step(req)

    def run_check(self, name, key, evidence, rungs=None):
        self._tick()
        return super().run_check(name, key, evidence, rungs)


CHECKS = {"c": lambda name, key, evidence: key != "b"}  # b's acceptance fails, deterministically


def _baseline(tmp, **kw):
    d = tmp / "base"
    d.mkdir()
    host = ScriptedHost(checks=CHECKS, **kw)
    return runtime(d, host=host).run("t", run_id=RID), len(host.calls)


@pytest.mark.parametrize("k", range(0, 6))
def test_a_run_killed_after_each_node_resumes_to_the_same_final_state(tmp_path, k):
    base, n = _baseline(tmp_path)
    assert base.status == "error" and k < n == 6
    rt = runtime(tmp_path, host=KillingHost(k, checks=CHECKS))
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    del rt
    gc.collect()  # the unwound generators record `cancelled`; a real crash would not
    entries = ort.RunLedger(tmp_path / "run.ledger", KEY).read()
    assert not any(e["kind"] == "log" and e["body"]["kind"] == "accept" and e["body"].get("status") == "cancelled"
                   for e in entries), "unwinding after the kill must not write to the ledger"
    live = ScriptedHost(checks=CHECKS)
    resumed = runtime(tmp_path, host=live).resume()
    assert summary(resumed) == summary(base)
    assert len(live.calls) == n - k  # journaled answers are not run again


def test_unwinding_siblings_after_a_kill_write_nothing_to_the_ledger(tmp_path):
    root = make_root(tmp_path, wf=doc(("par", {"fork": {"branches": [{"w": gate()}, {"s": leaf()}]}})))
    rt = runtime(tmp_path, root=root, host=KillingHost(0))
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    del rt
    gc.collect()
    entries = ort.RunLedger(tmp_path / "run.ledger", KEY).read()
    assert not any(e["kind"] == "log" and e["body"]["kind"] == "accept" for e in entries)


def test_resume_with_a_torn_last_line(tmp_path):
    base, n = _baseline(tmp_path)
    rt = runtime(tmp_path, host=KillingHost(3, checks=CHECKS))
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    path = tmp_path / "run.ledger"
    data = path.read_bytes()
    path.write_bytes(data + b'{"seq": 99, "prev": "abc')
    resumed = runtime(tmp_path, host=ScriptedHost(checks=CHECKS)).resume()
    assert summary(resumed) == summary(base)


def test_resume_refuses_when_the_workflow_changed_under_the_run(tmp_path):
    root = make_root(tmp_path)
    rt = runtime(tmp_path, root=root, host=KillingHost(2))
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    (root / "workflows" / "t.json").write_text(json.dumps(doc(("a", leaf()), ("z", leaf()))))
    res = runtime(tmp_path, root=root).resume()
    assert res.status == "refused" and "changed since the run started" in res.errors[0]


# ---------------------------------------------------------------- 3. signatures


def test_the_ring_verifies_against_the_signer_role_not_the_claimed_one():
    ring = fake_ring()
    assert ring.verify(ev(sig="by:pm"), "pm") is True
    assert ring.verify(ev(sig="by:pm"), "owner") is False  # signed by the wrong entity
    assert ring.verify(ev(sig="by:owner"), "pm") is False
    assert ring.verify({"type": "x", "data": {}}, "owner") is False  # unsigned
    assert ring.verify(ev(sig=None), "owner") is False
    assert ring.verify(ev(sig=["by:owner"]), "owner") is False  # not a string


def test_the_ring_never_verifies_for_an_unknown_role_and_list_shows_public_keys_only():
    ring = fake_ring()
    assert ring.verify(ev(sig="by:ghost"), "ghost") is False
    assert ring.list() == {"owner": ["ssh-ed25519 AAAAowner"], "pm": ["ssh-ed25519 AAAApm"]}


def test_revoke_removes_the_key():
    ring = fake_ring()
    ring.revoke("ssh-ed25519 AAAApm")
    assert ring.verify(ev(sig="by:pm"), "pm") is False
    assert ring.verify(ev(sig="by:owner"), "owner") is True


def test_a_ring_refuses_private_key_material():
    private = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    with pytest.raises(ort.OwnerKeyError):
        ort.KeyRing({"owner": [private]}, verifier=FakeVerifier())
    with pytest.raises(ort.OwnerKeyError):
        ort.load_ring("owner ssh-ed25519 AAAA\n" + private)


def test_the_module_has_no_signing_path():
    tree = ast.parse((SCRIPTS / "org_runtime.py").read_text())
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "sign" not in strings and "-Y sign" not in strings
    for n in ast.walk(tree):  # no argv list holds `-Y` followed by `sign`
        if isinstance(n, ast.List):
            vals = [e.value for e in n.elts if isinstance(e, ast.Constant)]
            assert not ("-Y" in vals and "sign" in vals)


def test_load_ring_parses_role_and_public_key_lines():
    ring = ort.load_ring("# keys\nowner ssh-ed25519 AAAAowner me@x\npm ssh-ed25519 AAAApm\n", verifier=FakeVerifier())
    assert ring.list() == {"owner": ["ssh-ed25519 AAAAowner me@x"], "pm": ["ssh-ed25519 AAAApm"]}


def gate_root(tmp, signer=None):
    return make_root(tmp, wf=doc(("gate", gate(signer))))


def test_r6_unsigned_decision_is_ignored_and_the_gate_keeps_waiting(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", sig=None)), (2, ev("gate"))])
    res = runtime(tmp_path, root=gate_root(tmp_path), host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    ignored = [e for e in res.events if e["kind"] == "ignored"]
    assert [e["reason"] for e in ignored] == ["not signed by the owner"]


def test_r32_a_gate_with_a_signer_ignores_the_owner_and_accepts_the_signer(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", sig="by:owner")), (2, ev("gate", sig="by:pm"))])
    res = runtime(tmp_path, root=gate_root(tmp_path, "pm"), host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    assert [e["reason"] for e in res.events if e["kind"] == "ignored"] == ["not signed by the pm"]


def test_the_ring_not_the_inner_host_decides(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", sig="by:owner"))], signed=lambda e, s: True)  # inner host says yes
    ring = fake_ring()
    ring.revoke("ssh-ed25519 AAAAowner")
    res = runtime(tmp_path, root=gate_root(tmp_path), host=host, ring=ring).run("t", run_id=RID)
    assert res.status == "error" and "timeout" in " ".join(res.errors).lower()


def test_r7_r8_r18_owner_reject_wrong_task_wrong_run(tmp_path):
    host = ScriptedHost(events=[(1, ev("other")), (2, ev("gate", run="f" * 32)), (3, ev("gate", "reject"))])
    res = runtime(tmp_path, root=gate_root(tmp_path), host=host).run("t", run_id=RID)
    assert res.status == "error" and "gate: decision rejected" in res.errors
    assert len([e for e in res.events if e["kind"] == "ignored"]) == 2


def test_replay_keeps_a_decision_after_the_key_is_revoked(tmp_path):
    root = gate_root(tmp_path)
    ring = fake_ring()
    live = runtime(tmp_path, root=root, host=ScriptedHost(events=[(1, ev("gate"))]), ring=ring).run("t", run_id=RID)
    assert live.status == "success"
    ring.revoke("ssh-ed25519 AAAAowner")
    again = runtime(tmp_path, root=root, host=ScriptedHost(events=[(1, ev("gate"))]), ring=ring).replay()
    assert summary(again) == summary(live)


# real signatures through ssh-keygen -------------------------------------------------


def keygen(tmp, name):
    path = tmp / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
    return path, (tmp / f"{name}.pub").read_text().strip()


def sign_event(event, key_path, ns=NS):
    """The owner's side. Lives in the tests: the runtime holds no signing code."""
    payload = ort.event_payload(event)
    out = subprocess.run(["ssh-keygen", "-Y", "sign", "-q", "-f", str(key_path), "-n", ns], input=payload,
                         capture_output=True, check=True).stdout.decode()
    return {**{k: v for k, v in event.items() if k != "signature"}, "signature": out}


def ssh_ring(tmp):
    owner_key, owner_pub = keygen(tmp, "owner")
    pm_key, pm_pub = keygen(tmp, "pm")
    # The same ssh-keygen that signed: the default lookup skips PATH by design, and a nix build sandbox has
    # ssh-keygen only on PATH (no /usr/bin, no profile), so the default verifier would fail closed there.
    verifier = ort.SshKeygenVerifier(ssh_keygen=shutil.which("ssh-keygen"))
    return ort.KeyRing({"owner": [owner_pub], "pm": [pm_pub]}, verifier=verifier), owner_key, pm_key


@needs_ssh
def test_real_signatures_verify_and_the_wrong_entity_is_rejected(tmp_path):
    ring, owner_key, pm_key = ssh_ring(tmp_path)
    good = sign_event(ev("gate", sig=None), owner_key)
    assert ring.verify(good, "owner") is True
    assert ring.verify(good, "pm") is False  # owner key is not pm's
    assert ring.verify(sign_event(ev("gate", sig=None), pm_key), "owner") is False
    forged = copy.deepcopy(good)
    forged["data"]["decision"] = "reject"  # payload changed after signing
    assert ring.verify(forged, "owner") is False
    assert ring.verify({**good, "signature": "garbage"}, "owner") is False


@needs_ssh
def test_a_signature_made_for_another_namespace_does_not_verify(tmp_path):
    ring, owner_key, _ = ssh_ring(tmp_path)
    event = ev("gate", sig=None)
    out = subprocess.run(["ssh-keygen", "-Y", "sign", "-q", "-f", str(owner_key), "-n", "git"],
                         input=ort.event_payload(event), capture_output=True, check=True).stdout.decode()
    assert ring.verify({**event, "signature": out}, "owner") is False


@needs_ssh
def test_a_signed_gate_run_end_to_end(tmp_path):
    ring, owner_key, pm_key = ssh_ring(tmp_path)
    events = [(1, sign_event(ev("gate", sig=None), owner_key)), (2, sign_event(ev("gate", sig=None), pm_key))]
    res = runtime(tmp_path, root=gate_root(tmp_path, "pm"), host=ScriptedHost(events=events), ring=ring).run(
        "t", run_id=RID)
    assert res.status == "success", res.errors
    assert len([e for e in res.events if e["kind"] == "ignored"]) == 1


# ---------------------------------------------------------------- 4. metrics through the catalog's collectors


def test_every_executed_node_records_its_metrics_through_the_collector(tmp_path):
    seen = []

    def collector(metric, entry, key, run_id, ledger_path):
        seen.append((metric, key, run_id))
        return 7

    rt = runtime(tmp_path, collector=collector)
    assert rt.run("t", run_id=RID).status == "success"
    assert seen == [("m1", "a", RID), ("m1", "b", RID), ("m1", "c", RID)]
    rows = [e["body"] for e in ort.RunLedger(tmp_path / "run.ledger", KEY).read() if e["kind"] == "metric"]
    assert rows == [{"key": k, "metric": "m1", "value": 7} for k in "abc"]


def test_a_node_whose_metric_has_no_collector_is_refused_at_load_not_at_run(tmp_path):
    root = make_root(tmp_path, collector=None)  # collectors/m1.py is absent
    host = ScriptedHost()
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "refused"
    assert res.errors[0].startswith("run refused: ") and "m1" in res.errors[0] and "collector" in res.errors[0]
    assert host.calls == []


def test_a_collector_that_cannot_run_records_an_error_never_zero(tmp_path):
    root = make_root(tmp_path, collector=STUB)
    rt = runtime(tmp_path, root=root, collector=ort.ProcessCollector(root))
    assert rt.run("t", run_id=RID).status == "success"
    rows = [e["body"] for e in ort.RunLedger(tmp_path / "run.ledger", KEY).read() if e["kind"] == "metric"]
    assert len(rows) == 3 and all("value" not in r and "not implemented" in r["error"] for r in rows)


def test_the_process_collector_reads_the_ledger_and_returns_a_number(tmp_path):
    root = make_root(tmp_path)
    rt = runtime(tmp_path, root=root, collector=ort.ProcessCollector(root))
    assert rt.run("t", run_id=RID).status == "success"
    rows = [e["body"] for e in ort.RunLedger(tmp_path / "run.ledger", KEY).read() if e["kind"] == "metric"]
    assert all(isinstance(r["value"], int) and r["value"] > 0 for r in rows)


def two_metric_root(tmp, collector=COLLECTOR):
    cat = {**CATALOG, "m2": {**CATALOG["m1"], "collector": "collectors/m2.py"}}
    root = make_root(tmp, wf=doc(("a", leaf(metrics=("m1", "m2"))), ("b", leaf(metrics=("m1", "m2")))), catalog=cat,
                     collector=collector)
    (root / "collectors" / "m2.py").write_text(collector)
    return root


def _rows(tmp):
    return [e["body"] for e in ort.RunLedger(tmp / "run.ledger", KEY).read() if e["kind"] == "metric"]


def test_a_kill_between_two_metric_rows_records_the_second_once_on_resume(tmp_path):
    root = two_metric_root(tmp_path)

    def dying(metric, entry, key, run_id, path):
        if (metric, key) == ("m2", "a"):
            raise Killed()
        return 1

    rt = runtime(tmp_path, root=root, collector=dying)
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    assert [(r["key"], r["metric"]) for r in _rows(tmp_path)] == [("a", "m1")]
    runtime(tmp_path, root=root, collector=lambda m, e, k, r, p: 1).resume()
    assert sorted((r["key"], r["metric"]) for r in _rows(tmp_path)) == [
        ("a", "m1"), ("a", "m2"), ("b", "m1"), ("b", "m2")]


def test_replay_never_runs_a_collector(tmp_path):
    root = two_metric_root(tmp_path)
    runtime(tmp_path, root=root).run("t", run_id=RID)
    boom = []
    rt = runtime(tmp_path, root=root, collector=lambda *a: boom.append(a))
    assert rt.replay().status == "success" and boom == []


def test_collectors_run_isolated_from_verified_bytes_with_no_ledger_path(tmp_path):
    script = ("import json, os, sys\n"
              "print(json.dumps(1 if 'ORG_LEDGER' not in os.environ and 'ORG_METRIC_INPUT' in os.environ and "
              "sys.flags.isolated else 0))\n")
    root = make_root(tmp_path, collector=script)
    rt = runtime(tmp_path, root=root, collector=ort.ProcessCollector(root))
    assert rt.run("t", run_id=RID).status == "success"
    assert [r["value"] for r in _rows(tmp_path)] == [1, 1, 1]


def test_a_collector_rewritten_after_load_still_runs_the_verified_bytes(tmp_path):
    root = make_root(tmp_path, collector="print(5)\n")

    def tamper(req):
        (root / "collectors" / "m1.py").write_text("print(99)\n")
        return {}

    rt = runtime(tmp_path, root=root, collector=ort.ProcessCollector(root), host=ScriptedHost(steps={"a": tamper}))
    assert rt.run("t", run_id=RID).status == "success"
    assert {r["value"] for r in _rows(tmp_path)} == {5}


def test_a_hanging_collector_is_killed_and_recorded_as_an_error(tmp_path):
    root = make_root(tmp_path, collector="import time\ntime.sleep(60)\n")
    rt = runtime(tmp_path, root=root, collector=ort.ProcessCollector(root, timeout=0.5),
                 host=ScriptedHost())
    started = time.monotonic()
    assert rt.run("t", run_id=RID).status == "success"
    assert time.monotonic() - started < 20
    assert all("timed out" in r["error"] for r in _rows(tmp_path))


# ---------------------------------------------------------------- 5. load refusals, R24, rungs


def test_r24_a_start_cycle_refuses_the_run_before_the_first_task(tmp_path):
    man = manifest(workflows={"a": {"path": "workflows/a.json", "floors": []},
                              "b": {"path": "workflows/b.json", "floors": []}})
    root = make_root(tmp_path, man=man)
    for me, other in (("a", "b"), ("b", "a")):
        call = {"run": {"workflow": {"namespace": "org", "name": other, "version": "1.0.0"}},
                "metadata": {"org": {"by": "code", "role": "worker", "metrics": ["m1"],
                                     "acceptance": [{"check": "c"}]}}}
        (root / "workflows" / f"{me}.json").write_text(json.dumps(doc(("go", call), name=me)))
    host = ScriptedHost()
    res = runtime(tmp_path, root=root, host=host).run("a", run_id=RID)
    assert res.status == "refused" and host.calls == []
    assert res.errors[0] == "run refused: manifest.json: manifest: workflows: start cycle 'a' -> 'b' -> 'a'"


def test_r24_yaml_manifest_names_the_yaml_file(tmp_path):
    yaml = pytest.importorskip("yaml", reason="PyYAML is optional")
    man = manifest(workflows={"a": {"path": "workflows/a.json", "floors": []},
                              "b": {"path": "workflows/b.json", "floors": []}})
    root = make_root(tmp_path, man=man)
    (root / "manifest.json").unlink()
    (root / "manifest.yaml").write_text(yaml.safe_dump(man))
    for me, other in (("a", "b"), ("b", "a")):
        call = {"run": {"workflow": {"namespace": "org", "name": other, "version": "1.0.0"}},
                "metadata": {"org": {"by": "code", "role": "worker", "metrics": ["m1"],
                                     "acceptance": [{"check": "c"}]}}}
        (root / "workflows" / f"{me}.json").write_text(json.dumps(doc(("go", call), name=me)))
    res = runtime(tmp_path, root=root).run("a", run_id=RID)
    assert res.errors[0].startswith("run refused: manifest.yaml: manifest: workflows: start cycle")


def test_a_workflow_that_fails_validation_refuses_the_run(tmp_path):
    bad = doc(("a", leaf(metrics=("nope",))))
    host = ScriptedHost()
    res = runtime(tmp_path, root=make_root(tmp_path, wf=bad), host=host).run("t", run_id=RID)
    assert res.status == "refused" and "nope" in res.errors[0] and host.calls == []


# ---- file maps


def test_file_map_holds_only_the_org_root_entries(tmp_path):
    root = make_root(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts" / "x.py").write_text("x")
    m = ort.build_file_map(root)
    assert m["manifest.json"] == (root / "manifest.json").read_bytes()
    assert "workflows/t.json" in m and "collectors/m1.py" in m and "scripts/x.py" not in m


def test_file_map_follows_a_symlink_that_stays_inside(tmp_path):
    root = make_root(tmp_path)
    os.symlink(root / "briefs" / "x.md", root / "briefs" / "y.md")
    assert ort.build_file_map(root)["briefs/y.md"] == b"brief"


def test_file_map_refuses_a_symlink_that_leaves_the_root_and_a_dangling_one(tmp_path):
    root = make_root(tmp_path)
    (tmp_path / "secret.txt").write_text("s")
    os.symlink(tmp_path / "secret.txt", root / "briefs" / "out.md")
    with pytest.raises(ort.FileMapError, match="briefs/out.md"):
        ort.build_file_map(root)
    os.unlink(root / "briefs" / "out.md")
    os.symlink(tmp_path / "missing", root / "briefs" / "gone.md")
    with pytest.raises(ort.FileMapError, match="briefs/gone.md"):
        ort.build_file_map(root)


def test_file_map_refuses_a_directory_symlink(tmp_path):
    root = make_root(tmp_path)
    os.symlink(root / "briefs", root / "criteria" / "d")
    with pytest.raises(ort.FileMapError, match="criteria/d"):
        ort.build_file_map(root)


def test_file_map_refuses_paths_that_collide_case_insensitively(tmp_path):
    root = make_root(tmp_path)
    (root / "briefs" / "A.md").write_text("1")
    (root / "briefs" / "a.md").write_text("2")
    if len(list((root / "briefs").glob("[aA].md"))) < 2:
        pytest.skip("the file system is case-insensitive: the collision cannot be created")
    with pytest.raises(ort.FileMapError, match="collide"):
        ort.build_file_map(root)


def test_collision_check_on_plain_maps():
    with pytest.raises(ort.FileMapError, match="collide"):
        ort.check_collisions(["briefs/A.md", "briefs/a.md"])
    with pytest.raises(ort.FileMapError, match="collide"):  # unicode normalisation
        ort.check_collisions(["briefs/é.md", "briefs/é.md"])
    ort.check_collisions(["briefs/a.md", "briefs/b.md"])


# ---- rungs and owner signatures


def snapshot(tmp, root, repo=None, frozen=None, signer="owner", store=None, root_id=ROOT_ID):
    store = store or ort.SnapshotStore(tmp / "signed")
    files = ort.build_file_map(root)
    outside = frozen.map() if frozen else {}
    store.add(store.next_event(files, outside, root_id), f"by:{signer}", files, outside)
    return store


def rt_with(tmp, root, store, frozen=None, **kw):
    return runtime(tmp, root=root, snapshots=store, frozen=frozen or ort.NO_OUTSIDE, **kw)


def test_an_unchanged_root_runs(tmp_path):
    root = make_root(tmp_path)
    res = rt_with(tmp_path, root, snapshot(tmp_path, root)).run("t", run_id=RID)
    assert res.status == "success", res.errors


def test_a_manifest_change_without_the_owner_signature_is_refused(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    man = json.loads((root / "manifest.json").read_text())
    man["vetoes"].append("anything goes")
    (root / "manifest.json").write_text(json.dumps(man))
    host = ScriptedHost()
    res = rt_with(tmp_path, root, store, host=host).run("t", run_id=RID)
    assert res.status == "refused" and host.calls == []
    assert res.errors[0] == "run refused: manifest.json: change needs rung 'frozen' and has no owner signature"


def test_a_signed_manifest_change_runs(tmp_path):
    root = make_root(tmp_path)
    snapshot(tmp_path, root)
    man = json.loads((root / "manifest.json").read_text())
    man["vetoes"].append("one more")
    (root / "manifest.json").write_text(json.dumps(man))
    store = snapshot(tmp_path, root)  # the owner signs the new version
    assert rt_with(tmp_path, root, store).run("t", run_id=RID).status == "success"


def test_a_snapshot_signed_by_another_role_does_not_count(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root, signer="pm")
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.status == "refused" and "no owner-signed snapshot" in res.errors[0]


def test_no_snapshot_at_all_refuses(tmp_path):
    root = make_root(tmp_path)
    res = rt_with(tmp_path, root, ort.SnapshotStore(tmp_path / "empty")).run("t", run_id=RID)
    assert res.status == "refused" and "no owner-signed snapshot" in res.errors[0]


def test_the_base_is_the_latest_valid_snapshot_and_a_forged_newer_one_is_skipped(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    (root / "briefs" / "x.md").write_text("edited")
    files = ort.build_file_map(root)
    store.add(store.next_event(files, {}, ROOT_ID), "by:pm", files, {})  # forged: not the owner's
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.status == "success", res.errors  # ordinary change, base is the owner's snapshot


def test_an_ordinary_change_is_allowed_for_the_default_proposer_and_refused_when_narrowed(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    (root / "briefs" / "x.md").write_text("edited")
    assert rt_with(tmp_path, root, store).run("t", run_id=RID).status == "success"
    res = rt_with(tmp_path, root, store, proposer_rungs=("free",)).run("t", run_id=RID)
    assert res.status == "refused"
    assert res.errors[0] == "run refused: briefs/x.md: change needs rung 'ordinary' and has no owner signature"


def test_a_floor_or_checks_change_is_frozen(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    (root / "checks" / "c.py").write_text("import sys\nsys.exit(1)\n")
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.errors[0] == "run refused: checks/c.py: change needs rung 'frozen' and has no owner signature"


def test_a_change_to_a_frozen_file_outside_the_org_root_is_refused(tmp_path):
    root = make_root(tmp_path)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "grammar.py").write_text("v1")
    (repo / "unlisted.txt").write_text("v1")
    frozen = ort.FrozenOutside(repo, ("scripts/", "hooks/hooks.json"))
    store = snapshot(tmp_path, root, frozen=frozen)
    (repo / "unlisted.txt").write_text("v2")
    assert rt_with(tmp_path, root, store, frozen=frozen).run("t", run_id=RID).status == "success"
    (repo / "scripts" / "grammar.py").write_text("v2")
    res = rt_with(tmp_path, root, store, frozen=frozen).run("t", run_id=RID)
    assert res.errors[0] == "run refused: scripts/grammar.py: change needs rung 'frozen' and has no owner signature"


def test_adding_or_removing_a_listed_outside_file_is_a_change(tmp_path):
    root = make_root(tmp_path)
    repo = tmp_path / "repo"
    (repo / "hooks").mkdir(parents=True)
    frozen = ort.FrozenOutside(repo, ("hooks/",))
    store = snapshot(tmp_path, root, frozen=frozen)
    (repo / "hooks" / "new.sh").write_text("x")
    res = rt_with(tmp_path, root, store, frozen=frozen).run("t", run_id=RID)
    assert res.status == "refused" and "hooks/new.sh" in res.errors[0]


def test_the_default_frozen_list_covers_the_grammar_hooks_plugin_metadata_and_tooling(tmp_path):
    repo = tmp_path / "repo"
    names = ["agents/operating-model/skills/workflow/scripts/validate_org.py",
             "agents/operating-model/skills/workflow/bindings/x.json", "agents/operating-model/skills/workflow/SKILL.md",
             "agents/operating-model/.claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
             "agents/operating-model/hooks/h.sh", ".claude/settings.json", "pyproject.toml", "uv.lock", "conftest.py",
             ".github/workflows/ci.yml"]
    for n in names:
        (repo / n).parent.mkdir(parents=True, exist_ok=True)
        (repo / n).write_text("x")
    (repo / "README.md").write_text("x")
    got = ort.FrozenOutside(repo, ort.DEFAULT_FROZEN_OUTSIDE).map()
    assert sorted(got) == sorted(names)


def test_a_frozen_path_with_dot_dot_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ort.FrozenOutside(tmp_path, ("../etc/passwd",))


def test_rungs_are_required_explicitly(tmp_path):
    with pytest.raises(TypeError):
        ort.OrgRuntime(make_root(tmp_path), ledger_path=tmp_path / "l", ledger_key=KEY, ring=fake_ring(),
                       host=ScriptedHost(), frozen=ort.NO_OUTSIDE)


# ---------------------------------------------------------------- real-time feed and driver


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.on_sleep = []

    def now(self):
        return self.t

    def sleep(self, dt):
        self.t += dt
        for at, fn in list(self.on_sleep):
            if self.t >= at:
                self.on_sleep.remove((at, fn))
                fn()


def test_inbox_feed_delivers_each_file_once_in_name_order(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "2.json").write_text(json.dumps({"type": "b"}))
    (inbox / "1.json").write_text(json.dumps({"type": "a"}))
    (inbox / "3.json").write_text("{not json")
    feed = ort.InboxFeed(inbox)
    assert [e["type"] for e in feed.poll()] == ["a", "b"]
    feed.ack()
    assert feed.poll() == []
    assert feed.rejected and "3.json" in feed.rejected[0]


def test_the_driver_delivers_a_live_event_to_a_waiting_gate(tmp_path):
    clock = FakeClock()
    feed = ort.QueueFeed()
    clock.on_sleep.append((30, lambda: feed.push(ev("gate"))))
    rt = runtime(tmp_path, root=gate_root(tmp_path), clock=clock.now, sleep=clock.sleep)
    res = rt.run("t", run_id=RID, feed=feed)
    assert res.status == "success", res.errors
    assert 30 <= res.now < 40  # woke at the event, not at the 1 hour timeout


def test_the_driver_ignores_an_unsigned_live_event_and_times_out(tmp_path):
    clock = FakeClock()
    feed = ort.QueueFeed()
    clock.on_sleep.append((5, lambda: feed.push(ev("gate", sig=None))))
    rt = runtime(tmp_path, root=gate_root(tmp_path), clock=clock.now, sleep=clock.sleep)
    res = rt.run("t", run_id=RID, feed=feed)
    assert res.status == "error" and "timeout" in " ".join(res.errors).lower()
    assert [e["reason"] for e in res.events if e["kind"] == "ignored"] == ["not signed by the owner"]
    assert 3600 <= clock.t < 3700


def test_live_events_are_journaled_in_the_ledger(tmp_path):
    clock = FakeClock()
    feed = ort.QueueFeed()
    clock.on_sleep.append((30, lambda: feed.push(ev("gate"))))
    rt = runtime(tmp_path, root=gate_root(tmp_path), clock=clock.now, sleep=clock.sleep)
    rt.run("t", run_id=RID, feed=feed)
    kinds = [e["kind"] for e in ort.RunLedger(tmp_path / "run.ledger", KEY).read()]
    assert "feed" in kinds


def test_a_closed_feed_with_a_gate_timer_still_times_out(tmp_path):
    clock = FakeClock()
    feed = ort.QueueFeed()
    feed.close()
    rt = runtime(tmp_path, root=gate_root(tmp_path), clock=clock.now, sleep=clock.sleep)
    res = rt.run("t", run_id=RID, feed=feed)
    assert res.status == "error" and "timeout" in " ".join(res.errors).lower() and clock.t >= 3600


def test_the_live_scheduler_reports_a_deadlock_when_the_feed_is_closed_and_nothing_can_wake():
    clock = FakeClock()
    feed = ort.QueueFeed()
    sched = ort.LiveScheduler([], feed, clock.now, clock.sleep, lambda t, e: None, 1.0)

    def waiter():
        yield it.WaitEvent(lambda e: None, None)  # no deadline: only an event can wake it

    sched.spawn(waiter())
    feed.close()
    assert sched.run() is False
    open_feed = ort.QueueFeed()
    sched2 = ort.LiveScheduler([], open_feed, clock.now, clock.sleep, lambda t, e: None, 1.0)
    sched2.spawn(waiter())
    clock.on_sleep.append((clock.t + 5, lambda: open_feed.push({"type": "x"})))
    clock.on_sleep.append((clock.t + 6, open_feed.close))
    assert sched2.run() is False  # the event matched nothing; closing the feed ends the wait


# ---------------------------------------------------------------- model judge and agent-run environment


def judge_setup(tmp, script):
    root = make_root(tmp)
    sess = tmp / "sessions"
    sess.mkdir()
    script_path = tmp / "script.json"
    script_path.write_text(json.dumps(script))
    inp = sess / "input-1.json"
    inp.write_text(json.dumps({"run": RID, "key": "gate", "input": {"item": 0, "output": "o"}, "reasons": {}}))
    host = ort.OrgProcessHost(root, session_dir=sess,
                              env={"ORG_TEST_HARNESS": "1", "ORG_HARNESS": "scripted", "ORG_HARNESS_SCRIPT": str(script_path)})
    req = JudgeRequest(key="gate", item=0, role="reviewer", rubric="criteria/q.md", run_id=RID, invocation="i-1",
                       input_file=str(inp),
                       argv=["agent-run", "--role", "reviewer", "--brief", "criteria/q.md", "--input", str(inp)])
    return host, req


@pytest.mark.parametrize("verdict", ["pass", "fail"])
def test_run_judge_runs_agent_run_and_returns_a_typed_verdict(tmp_path, verdict):
    host, req = judge_setup(tmp_path, [{"result": "ok", "verdict": verdict}])
    reply = host.run_judge(req)
    assert reply["invocation"] == "i-1" and reply["type"] == "org.rubric-verdict"
    assert reply["data"] == {"run": RID, "task": "gate", "item": 0, "verdict": verdict}


def test_run_judge_returns_none_when_agent_run_fails(tmp_path):
    host, req = judge_setup(tmp_path, [])  # script exhausted: agent-run exits 1
    assert host.run_judge(req) is None


def test_run_judge_rejects_a_verdict_for_another_task(tmp_path, monkeypatch):
    host, req = judge_setup(tmp_path, [{"result": "ok", "verdict": "pass"}])
    req.key = "other"  # the input file names `gate`: agent-run refuses the mismatch
    assert host.run_judge(req) is None


def test_agent_run_steps_get_the_session_dir_from_the_runtime(tmp_path):
    host, req = judge_setup(tmp_path, [{"result": "built"}])
    step = it.StepRequest(key="gate", command="agent-run", run_id=RID,
                          argv=["agent-run", "--role", "worker", "--brief", "briefs/x.md"], input=None)
    out = host.run_step(step)
    assert out.exit_code == 0, out.error
    assert (tmp_path / "sessions").exists() and any((tmp_path / "sessions").iterdir())


def test_a_judge_through_the_whole_runtime(tmp_path):
    sess = tmp_path / "sessions"
    script = tmp_path / "script.json"
    script.write_text(json.dumps([{"result": "ok", "verdict": "pass"}]))
    task = leaf(by="model")
    task["metadata"]["org"]["acceptance"] = [{"rubric": "criteria/q.md", "judge": "reviewer"}]
    task["run"]["shell"]["command"] = "agent-run"
    task["metadata"]["org"]["brief"] = "briefs/x.md"
    root = make_root(tmp_path, wf=doc(("a", task)))
    # each agent-run process reads the script from the start, so one reply serves the step and the judge
    script.write_text(json.dumps([{"result": "ok", "verdict": "pass"}]))
    host = ort.OrgProcessHost(root, session_dir=sess, env={"ORG_TEST_HARNESS": "1", "ORG_HARNESS": "scripted", "ORG_HARNESS_SCRIPT": str(script)})
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    assert [e["result"] for e in res.events if e["kind"] == "item"] == ["pass"]


# ================================================================ review 1

LEDGER = lambda tmp: ort.RunLedger(tmp / "run.ledger", KEY)  # noqa: E731


def ids_in(tmp):
    return [e["body"] for e in LEDGER(tmp).read() if e["kind"] == "decision-id"]


# ---- B1: decision events carry an id and each id is consumed once per run (P33)


def test_a_decision_event_without_an_id_is_ignored(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", id=False)), (2, ev("gate", id="ok-1"))])
    res = runtime(tmp_path, root=gate_root(tmp_path), host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    assert [e["reason"] for e in res.events if e["kind"] == "ignored"] == ["event has no id"]


def test_a_decision_event_with_a_non_string_or_empty_id_is_ignored(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", id=5)), (2, ev("gate", id="")), (3, ev("gate", id="ok-1"))])
    res = runtime(tmp_path, root=gate_root(tmp_path), host=host).run("t", run_id=RID)
    assert [e["reason"] for e in res.events if e["kind"] == "ignored"] == ["event has no id"] * 2


def test_r45_the_same_decision_id_in_the_next_round_is_ignored(tmp_path):
    loop = {"for": {"in": [1, 2], "each": "n"}, "while": "${ true }", "do": [{"g": gate()}]}
    root = make_root(tmp_path, wf=doc(("r", loop)))
    host = ScriptedHost(events=[(1, ev("r/g", id="same")), (5, ev("r/g", id="same", reason="again"))])
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "error" and "timeout" in " ".join(res.errors).lower()
    assert [e["reason"] for e in res.events if e["kind"] == "ignored"] == ["decision event already consumed"]
    assert ids_in(tmp_path) == [{"id": "same", "key": "r/g"}]


def test_decision_ids_survive_a_resume(tmp_path):
    root = make_root(tmp_path, wf=doc(("gate", gate()), ("b", leaf())))
    events = [(1, ev("gate", id="x"))]
    with pytest.raises(Killed):
        runtime(tmp_path, root=root, host=KillingHost(0, events=events)).run("t", run_id=RID)
    assert ids_in(tmp_path) == [{"id": "x", "key": "gate"}]
    res = runtime(tmp_path, root=root, host=ScriptedHost(events=events)).resume()
    assert res.status == "success", res.errors
    assert ids_in(tmp_path) == [{"id": "x", "key": "gate"}]  # recorded once, not again


# ---- B2: a live-fed run replays and resumes faithfully


def test_kill_while_a_gate_waits_then_resume_with_a_feed_and_approve(tmp_path):
    root = gate_root(tmp_path)
    c1, f1 = FakeClock(), ort.QueueFeed()
    c1.on_sleep.append((5, lambda: f1.push(ev("gate", sig=None, id="u-1"))))

    def die():
        raise Killed()

    c1.on_sleep.append((50, die))
    with pytest.raises(Killed):
        runtime(tmp_path, root=root, clock=c1.now, sleep=c1.sleep).run("t", run_id=RID, feed=f1)
    c2, f2 = FakeClock(), ort.QueueFeed()
    c2.on_sleep.append((20, lambda: f2.push(ev("gate", id="approve-1"))))
    res = runtime(tmp_path, root=root, clock=c2.now, sleep=c2.sleep).resume(feed=f2)
    assert res.status == "success", res.errors
    assert [e["reason"] for e in res.events if e["kind"] == "ignored"] == ["not signed by the owner"]
    feeds = [e["body"]["event"]["id"] for e in LEDGER(tmp_path).read() if e["kind"] == "feed"]
    assert feeds == ["u-1", "approve-1"]


def test_a_resumed_gate_still_times_out_on_its_original_deadline(tmp_path):
    root = gate_root(tmp_path)
    c1, f1 = FakeClock(), ort.QueueFeed()

    def die():
        raise Killed()

    c1.on_sleep.append((100, die))
    with pytest.raises(Killed):
        runtime(tmp_path, root=root, clock=c1.now, sleep=c1.sleep).run("t", run_id=RID, feed=f1)
    c2 = FakeClock()
    res = runtime(tmp_path, root=root, clock=c2.now, sleep=c2.sleep).resume(feed=ort.QueueFeed())
    assert res.status == "error" and "timeout" in " ".join(res.errors).lower()
    assert 3500 <= c2.t <= 3700  # the hour restarts from the last journaled moment, not from zero twice


def test_a_long_step_then_a_gate_replays_without_divergence(tmp_path):
    root = make_root(tmp_path, wf=doc(("a", leaf()), ("gate", gate())))
    clock, feed = FakeClock(), ort.QueueFeed()
    clock.on_sleep.append((3700, lambda: feed.push(ev("gate", id="late"))))  # 700 s into the gate
    host = ScriptedHost(steps={"a": {"duration": 3000}})
    live = runtime(tmp_path, root=root, host=host, clock=clock.now, sleep=clock.sleep).run("t", run_id=RID, feed=feed)
    assert live.status == "success", live.errors
    again = runtime(tmp_path, root=root, host=ScriptedHost()).replay()
    assert summary(again) == summary(live)


def test_a_step_run_live_during_replay_does_not_wait_twice(tmp_path):
    root = make_root(tmp_path, wf=doc(("a", leaf()), ("b", leaf())))
    c1 = FakeClock()
    with pytest.raises(Killed):  # a step, its check, then b's step: killed on the third call
        runtime(tmp_path, root=root, host=KillingHost(2), clock=c1.now, sleep=c1.sleep).run(
            "t", run_id=RID, feed=ort.QueueFeed())
    c2 = FakeClock()

    def slow(req):  # a real host blocks for the step's duration and reports it
        c2.t += 40
        return {"duration": 40}

    res = runtime(tmp_path, root=root, host=ScriptedHost(steps={"b": slow}), clock=c2.now, sleep=c2.sleep).resume(
        feed=ort.QueueFeed())
    assert res.status == "success", res.errors
    assert c2.t <= 45  # the 40 s already passed on the wall clock are not waited a second time


def test_the_journal_keeps_real_step_durations_in_live_mode(tmp_path):
    root = make_root(tmp_path, wf=doc(("a", leaf())))
    clock = FakeClock()
    runtime(tmp_path, root=root, host=ScriptedHost(steps={"a": {"duration": 12.5}}), clock=clock.now,
            sleep=clock.sleep).run("t", run_id=RID, feed=ort.QueueFeed())
    steps = [e["body"]["result"] for e in LEDGER(tmp_path).read() if e["kind"] == "host" and e["body"]["call"] == "step"]
    assert [s["duration"] for s in steps] == [12.5]


# ---- B3: check time versus use time


def test_the_load_reads_the_verified_bytes_not_the_disk(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    real = ort.build_file_map

    def build(r):
        m = real(r)
        (root / "workflows" / "t.json").write_text(json.dumps(doc(("zzz", leaf()))))  # swapped after the map
        return m

    monkeypatch.setattr(ort, "build_file_map", build)
    res = runtime(tmp_path, root=root).run("t", run_id=RID)
    assert res.status == "success" and set(res.statuses) == {"a", "b", "c"}


def test_a_step_that_rewrites_a_check_makes_the_next_check_refuse(tmp_path):
    root = make_root(tmp_path)

    def tamper(req):
        (root / "checks" / "c.py").write_text("import sys\nsys.exit(0)\n# edited\n")
        return {}

    host = ScriptedHost(steps={"a": tamper})
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "error" and any("checks/c.py" in e and "changed" in e for e in res.errors)
    assert ("check", "c", "a") not in host.calls


def test_a_step_that_rewrites_a_bin_program_makes_the_next_step_refuse(tmp_path):
    root = make_root(tmp_path)

    def tamper(req):
        (root / "bin" / "work").write_text("#!/bin/sh\nrm -rf /\n")
        return {}

    host = ScriptedHost(steps={"a": tamper})
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "error" and any("bin/work" in e and "changed" in e for e in res.errors)
    assert [c for c in host.calls if c[0] == "step"] == [("step", "work", "a")]


# ---- B4: snapshots are a signed, monotonic chain


def store_dir(tmp):
    return tmp / "signed"


def test_a_snapshot_chain_gets_seq_and_prev(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    snapshot(tmp_path, root, store=store)
    rows = [json.loads(line) for line in (store_dir(tmp_path) / "snapshots.jsonl").read_text().splitlines()]
    assert [r["data"]["seq"] for r in rows] == [1, 2] and rows[0]["data"]["prev"] != rows[1]["data"]["prev"]
    assert all(r["data"]["root_id"] == ROOT_ID for r in rows)


def test_an_older_signed_line_appended_to_the_store_refuses_the_run(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    snapshot(tmp_path, root, store=store)
    path = store_dir(tmp_path) / "snapshots.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines + [lines[0]]) + "\n")
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.status == "refused" and "out of sequence" in res.errors[0]


def test_truncating_the_newest_snapshots_is_caught_when_the_run_resumes(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    snapshot(tmp_path, root, store=store)
    with pytest.raises(Killed):
        rt_with(tmp_path, root, store, host=KillingHost(1)).run("t", run_id=RID)
    header = LEDGER(tmp_path).read()[0]["body"]
    assert header["snapshot"]["seq"] == 2
    path = store_dir(tmp_path) / "snapshots.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    res = rt_with(tmp_path, root, store).resume()
    assert res.status == "refused" and "snapshot" in res.errors[0] and "older" in res.errors[0]


def test_a_missing_blob_refuses_the_run_without_falling_back(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    (root / "briefs" / "x.md").write_text("changed once")
    snapshot(tmp_path, root, store=store)
    blob = store_dir(tmp_path) / "blobs" / ort.hashlib.sha256(b"changed once").hexdigest()
    blob.unlink()
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.status == "refused" and "blob" in res.errors[0]


def test_a_snapshot_of_another_root_is_ignored(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root, root_id="some-other-root")
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.status == "refused" and "no owner-signed snapshot" in res.errors[0]
    snapshot(tmp_path, root, store=store)  # ours starts its own chain at seq 1
    assert rt_with(tmp_path, root, store).run("t2-" + RID[:8] if False else "t", run_id="f" * 32).status == "success"


def test_odd_lines_in_the_snapshot_store_are_ignored(tmp_path):
    root = make_root(tmp_path)
    store = snapshot(tmp_path, root)
    path = store_dir(tmp_path) / "snapshots.jsonl"
    path.write_text("[]\n5\n{\"data\": 1}\nnot json\n" + path.read_text())
    assert rt_with(tmp_path, root, store).run("t", run_id=RID).status == "success"


@needs_ssh
def test_real_signed_snapshots_and_namespaces(tmp_path):
    ring, owner_key, pm_key = ssh_ring(tmp_path)
    root = make_root(tmp_path)
    files = ort.build_file_map(root)

    def add(store, key, ns):
        event = store.next_event(files, {}, ROOT_ID)
        store.add(event, sign_event(event, key, ns)["signature"], files, {})
        return store

    good = add(ort.SnapshotStore(tmp_path / "good"), owner_key, "org-snapshot")
    assert rt_with(tmp_path, root, good, ring=ring).run("t", run_id=RID).status == "success"
    for name, key, ns in (("evns", owner_key, NS), ("pm", pm_key, "org-snapshot")):
        bad = add(ort.SnapshotStore(tmp_path / f"store-{name}"), key, ns)
        res = rt_with(tmp_path, root, bad, ring=ring).run("t", run_id="e" * 32)
        assert res.status == "refused" and "no owner-signed snapshot" in res.errors[0], name
    event = ev("gate", sig=None)  # and a snapshot-namespace signature is no decision
    snap_sig = sign_event(event, owner_key, "org-snapshot")
    assert ring.verify(snap_sig, "owner") is False


# ---- B5: ledger rollback


def head_of(tmp):
    return json.loads(Path(str(tmp / "run.ledger") + ".head").read_text())


def test_a_head_file_follows_every_append(tmp_path):
    runtime(tmp_path).run("t", run_id=RID)
    entries = LEDGER(tmp_path).read()
    head = head_of(tmp_path)
    assert head["run_id"] == RID and head["count"] == len(entries) and head["last"] == entries[-1]["mac"]


def test_a_ledger_cut_back_to_an_earlier_entry_is_refused_on_resume(tmp_path):
    runtime(tmp_path).run("t", run_id=RID)
    path = tmp_path / "run.ledger"
    path.write_text("\n".join(path.read_text().splitlines()[:6]) + "\n")
    with pytest.raises(ort.LedgerError, match="shorter"):
        runtime(tmp_path).resume()


def test_a_deleted_or_forged_head_file_is_refused(tmp_path):
    runtime(tmp_path).run("t", run_id=RID)
    headp = Path(str(tmp_path / "run.ledger") + ".head")
    forged = {**head_of(tmp_path), "count": 2}
    headp.write_text(json.dumps(forged))
    with pytest.raises(ort.LedgerError, match="head"):
        runtime(tmp_path).resume()
    headp.unlink()
    with pytest.raises(ort.LedgerError, match="head"):
        runtime(tmp_path).resume()


def test_a_ledger_of_another_run_is_refused(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    runtime(other).run("t", run_id="a" * 32)
    runtime(tmp_path).run("t", run_id=RID)
    shutil.copy(other / "run.ledger", tmp_path / "run.ledger")
    with pytest.raises(ort.LedgerError, match="run id"):
        runtime(tmp_path).resume()


def test_resume_takes_an_expected_head(tmp_path):
    runtime(tmp_path).run("t", run_id=RID)
    head = head_of(tmp_path)
    assert runtime(tmp_path).resume(expected_head=(head["count"], head["last"])).status == "success"
    with pytest.raises(ort.LedgerError, match="expected"):
        runtime(tmp_path).resume(expected_head=(head["count"] + 5, head["last"]))
    with pytest.raises(ort.LedgerError, match="expected"):
        runtime(tmp_path).resume(expected_head=(head["count"], "0" * 64))


def test_a_short_ledger_key_is_refused_and_a_ledger_must_be_valid_utf8(tmp_path):
    with pytest.raises(ValueError, match="32"):
        ort.RunLedger(tmp_path / "x", b"short")
    runtime(tmp_path).run("t", run_id=RID)
    path = tmp_path / "run.ledger"
    path.write_bytes(path.read_bytes().replace(b"run-start", b"run-st\xffrt"))
    with pytest.raises(ort.LedgerError):
        LEDGER(tmp_path).read()


# ---- S1: run ids


def test_a_caller_chosen_run_id_is_refused_without_allow_run_id(tmp_path):
    with pytest.raises(ValueError, match="allow_run_id"):
        runtime(tmp_path, allow_run_id=False).run("t", run_id=RID)
    assert runtime(tmp_path, allow_run_id=False).run("t").status == "success"


def test_a_run_id_an_earlier_ledger_used_is_refused(tmp_path):
    runtime(tmp_path).run("t", run_id=RID)
    two = ort.OrgRuntime(tmp_path / "org", ledger_path=tmp_path / "two.ledger", ledger_key=KEY, ring=fake_ring(),
                         host=ScriptedHost(), snapshots=ort.UNENFORCED, frozen=ort.NO_OUTSIDE, allow_run_id=True,
                         collector=lambda *a: 0, root_id=ROOT_ID)
    with pytest.raises(ValueError, match="already used"):
        two.run("t", run_id=RID)


# ---- S3: the inbox feed


def test_the_inbox_rejects_symlinks_fifos_nan_and_deep_nesting_without_hanging(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "1.json").write_text(json.dumps({"type": "ok"}))
    (tmp_path / "outside.json").write_text(json.dumps({"type": "outside"}))
    os.symlink(tmp_path / "outside.json", inbox / "2.json")
    (inbox / "3.json").write_text('{"type": NaN}')
    (inbox / "4.json").write_text("[" * 100000 + "]" * 100000)
    os.mkfifo(inbox / "5.json")
    (inbox / "6.json").write_text('{"type": Infinity}')
    feed = ort.InboxFeed(inbox)
    assert [e["type"] for e in feed.poll()] == ["ok"]
    assert len(feed.rejected) == 5


def test_the_inbox_renames_a_file_only_after_ack(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "1.json").write_text(json.dumps({"type": "a"}))
    feed = ort.InboxFeed(inbox)
    assert len(feed.poll()) == 1 and (inbox / "1.json").exists()
    feed.ack()
    assert not (inbox / "1.json").exists() and (inbox / "1.seen").exists()


def test_the_inbox_caps_events_per_poll_and_per_run(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    for i in range(150):
        (inbox / f"{i:03d}.json").write_text(json.dumps({"type": "a", "n": i}))
    feed = ort.InboxFeed(inbox)
    first = feed.poll()
    feed.ack()
    assert len(first) == 100 and len(feed.poll()) == 50
    capped = ort.InboxFeed(inbox, max_total=2)
    (inbox / "x.json").write_text(json.dumps({"type": "a"}))
    assert len(capped.poll()) == 2
    capped.ack()
    assert capped.poll() == [] and any("run cap" in r for r in capped.rejected)


def test_the_driver_journals_before_the_inbox_renames(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    clock = FakeClock()
    feed = ort.InboxFeed(inbox)
    clock.on_sleep.append((5, lambda: (inbox / "1.json").write_text(json.dumps(ev("gate", id="f-1")))))
    runtime(tmp_path, root=gate_root(tmp_path), clock=clock.now, sleep=clock.sleep).run("t", run_id=RID, feed=feed)
    assert (inbox / "1.seen").exists()
    assert [e["body"]["event"]["id"] for e in LEDGER(tmp_path).read() if e["kind"] == "feed"] == ["f-1"]


def test_a_feed_event_that_is_not_json_is_rejected_not_fatal(tmp_path):
    feed = ort.QueueFeed()
    feed.push({"x": float("nan")})
    feed.push({"x": {1, 2}})
    feed.push(ev("gate", id="fine"))
    assert [e["id"] for e in feed.poll()] == ["fine"] and len(feed.rejected) == 2


# ---- S4: ssh-keygen path


def test_ssh_keygen_is_resolved_once_from_a_trusted_path(tmp_path, monkeypatch):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "ssh-keygen").write_text("#!/bin/sh\nexit 0\n")
    os.chmod(fake / "ssh-keygen", 0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    v = ort.SshKeygenVerifier()
    assert v.verify("owner", ["ssh-ed25519 AAAAx"], b"p", "sig", "org-event") is False
    assert v.path is None or not v.path.startswith(str(fake))


# ---- S5: the live scheduler equals the base scheduler


def kinds_of(res):
    return [(e["kind"], e.get("key")) for e in res.events]


def _two_ways(tmp, wf, pushes, steps=None):
    """Same scenario on the base scheduler (host events) and on the live one (a feed at the same times)."""
    root = make_root(tmp, wf=wf)
    base = runtime(tmp / "b", root=root, host=ScriptedHost(events=[(t, e) for t, e in pushes], steps=steps)) \
        if (tmp / "b").mkdir() is None else None
    live_dir = tmp / "l"
    live_dir.mkdir()
    clock, feed = FakeClock(), ort.QueueFeed()
    for t, e in pushes:
        clock.on_sleep.append((t, lambda e=e: feed.push(e)))
    live = runtime(live_dir, root=root, host=ScriptedHost(steps=steps), clock=clock.now, sleep=clock.sleep)
    return base.run("t", run_id=RID), live.run("t", run_id=RID, feed=feed)


@pytest.mark.parametrize("name,pushes", [
    ("approve", [(30, ev("gate", id="1"))]),
    ("ignored then approve", [(5, ev("gate", sig=None, id="1")), (9, ev("gate", id="2"))]),
    ("wrong task then reject", [(4, ev("zzz", id="1")), (8, ev("gate", "reject", id="2"))]),
    ("timeout", []),
])
def test_the_live_scheduler_gives_the_same_events_as_the_base_scheduler(tmp_path, name, pushes):
    base, live = _two_ways(tmp_path, doc(("gate", gate())), pushes)
    assert kinds_of(live) == kinds_of(base) and live.status == base.status and live.errors == base.errors


def test_the_live_scheduler_matches_the_base_on_parallel_steps(tmp_path):
    wf = doc(("par", {"fork": {"branches": [{"p": leaf()}, {"q": leaf()}]}}), ("z", leaf()))
    steps = {"p": {"duration": 10}, "q": {"duration": 20}}
    base, live = _two_ways(tmp_path, wf, [], steps=steps)
    assert kinds_of(live) == kinds_of(base) and summary(live) == summary(base)


# ---- S6: outside paths and maps


def test_frozen_outside_needs_a_repo_and_paths_unless_no_outside_is_explicit(tmp_path):
    with pytest.raises(ValueError):
        ort.FrozenOutside(None, ("a/",))
    with pytest.raises(ValueError):
        ort.FrozenOutside(tmp_path, ())
    assert ort.NO_OUTSIDE.map() == {}


def test_maps_exclude_pycache_and_pyc(tmp_path):
    root = make_root(tmp_path)
    (root / "briefs" / "__pycache__").mkdir()
    (root / "briefs" / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
    (root / "briefs" / "stray.pyc").write_bytes(b"\0")
    assert not [k for k in ort.build_file_map(root) if "pyc" in k or "__pycache__" in k]
    repo = tmp_path / "repo"
    (repo / "scripts" / "__pycache__").mkdir(parents=True)
    (repo / "scripts" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    (repo / "scripts" / "a.py").write_text("x")
    assert list(ort.FrozenOutside(repo, ("scripts/",)).map()) == ["scripts/a.py"]


# ---- S8: escapes become located errors


def fake_agent_run(tmp, body):
    path = tmp / "fake_agent_run.py"
    path.write_text(body)
    return str(path)


def step_req(tmp, **kw):
    inp = tmp / "tasks" / "input-1.json"
    inp.parent.mkdir(exist_ok=True)
    inp.write_text(json.dumps({"run": RID, "key": "gate", "input": None, "reasons": {}}))
    return it.StepRequest(key="gate", command="agent-run", run_id=RID, input_file=str(inp),
                          argv=["agent-run", "--role", "worker", "--brief", "briefs/x.md", "--input", str(inp)], **kw)


def test_staging_the_input_file_failing_is_an_error_outcome_not_a_traceback(tmp_path):
    root = make_root(tmp_path)
    sess = tmp_path / "sessions"
    sess.mkdir()
    (sess / "inputs").write_text("a file where the staging directory should be")
    host = ort.OrgProcessHost(root, session_dir=sess, agent_run=fake_agent_run(tmp_path, "print('{}')"))
    out = host.run_step(step_req(tmp_path))
    assert out.exit_code != 0 and "input" in out.error


def test_agent_run_gets_the_login_names_the_claude_child_needs_but_no_other_host_variable(tmp_path):
    # live smoke: without HOME and USER the claude child cannot find its login ("OAuth session expired")
    root = make_root(tmp_path)
    script = fake_agent_run(tmp_path, "import json, os, sys\nprint(json.dumps(dict(os.environ)))\n")
    env = {"HOME": "/h", "USER": "u", "LOGNAME": "u", "GITHUB_TOKEN": "t", "EXTRA_OK": "x", "ORG_CHILD_ENV_ALLOW": "EXTRA_OK"}
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "s", agent_run=script, env=env)
    got = host.run_step(step_req(tmp_path)).output
    assert got["HOME"] == "/h" and got["USER"] == "u" and got["LOGNAME"] == "u" and got["EXTRA_OK"] == "x"
    assert "GITHUB_TOKEN" not in got


def test_agent_run_output_that_is_not_utf8_does_not_raise(tmp_path):
    root = make_root(tmp_path)
    script = fake_agent_run(tmp_path, "import sys\nsys.stdout.buffer.write(b'\\xff\\xfe')\n")
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "s", agent_run=script)
    out = host.run_step(step_req(tmp_path))
    assert out.exit_code == 0 and isinstance(out.stdout, str)


@pytest.mark.parametrize("payload", ['{"event": {"type": "org.rubric-verdict", "data": 5}}', '{"event": 5}', "[]", "\\xff"])
def test_run_judge_with_odd_agent_output_is_none(tmp_path, payload):
    root = make_root(tmp_path)
    body = f"import sys\nsys.stdout.buffer.write(b{payload!r})\n" if payload == "\\xff" else \
        f"import sys\nsys.stdout.write({payload!r})\n"
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "s", agent_run=fake_agent_run(tmp_path, body))
    req = JudgeRequest(key="gate", item=0, role="reviewer", rubric="criteria/q.md", run_id=RID, invocation="i",
                       input_file=str(tmp_path / "in.json"),
                       argv=["agent-run", "--role", "reviewer", "--brief", "criteria/q.md"])
    assert host.run_judge(req) is None


def test_killing_a_process_group_that_is_gone_does_not_raise():
    ort.OrgProcessHost._killpg(2**22 - 3)


def test_a_session_dir_given_as_a_symlink_is_compared_by_real_path(tmp_path):
    root = make_root(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    os.symlink(real, tmp_path / "link")
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "link", agent_run=fake_agent_run(tmp_path, "print('{}')"))
    inp = real / "in.json"
    inp.write_text("{}")
    argv = ["agent-run", "--input", str(inp)]
    assert host._stage_input(argv, str(inp)) == argv  # already inside the session directory


# ---- nits


def test_principal_and_key_patterns_match_the_whole_string():
    assert ort.PRINCIPAL.fullmatch("pm\n") is None and ort.PRINCIPAL.fullmatch("pm") is not None
    assert ort.KEY_LINE.fullmatch("ssh-ed25519 AAAA\nx") is None


def test_the_verify_journal_key_includes_the_signature(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", sig="by:owner", id="1")), (2, ev("gate", sig="by:pm", id="2"))])
    runtime(tmp_path, root=gate_root(tmp_path, "pm"), host=host).run("t", run_id=RID)
    keys = [e["body"]["key"] for e in LEDGER(tmp_path).read() if e["kind"] == "host" and e["body"]["call"] == "verify"]
    assert len(keys) == 2 and len(set(keys)) == 2


def test_proposer_rungs_never_include_frozen(tmp_path):
    with pytest.raises(ValueError, match="frozen"):
        runtime(tmp_path, proposer_rungs=("free", "frozen"))


# ---- integration: ControlFlow, one id authority


def test_ledger_and_divergence_errors_pass_through_the_interpreter():
    assert issubclass(ort.LedgerError, it.ControlFlow) and issubclass(ort.DivergenceError, it.ControlFlow)
    assert not issubclass(ort.IntegrityError, it.ControlFlow)  # a changed file is a located run error


def test_replaying_an_unfinished_run_raises_the_ledger_error_not_a_run_error(tmp_path):
    with pytest.raises(Killed):
        runtime(tmp_path, host=KillingHost(2, checks=CHECKS)).run("t", run_id=RID)
    with pytest.raises(ort.LedgerError, match="replay"):
        runtime(tmp_path).replay()


def test_a_resume_that_diverges_from_the_ledger_raises_a_divergence_error(tmp_path):
    root = make_root(tmp_path, wf=doc(("gate", gate()), ("b", leaf())))
    with pytest.raises(Killed):
        runtime(tmp_path, root=root, host=KillingHost(0, events=[(1, ev("gate", id="x"))])).run("t", run_id=RID)
    other = ScriptedHost(events=[(1, ev("gate", "reject", id="x"))])
    with pytest.raises(ort.DivergenceError):
        runtime(tmp_path, root=root, host=other).resume()


def test_the_interpreter_is_the_one_authority_on_ids_and_the_ledger_only_records(tmp_path):
    host = ScriptedHost(events=[(1, ev("gate", id=False)), (2, ev("gate", id="x")), (3, ev("gate", id="x"))])
    res = runtime(tmp_path, root=gate_root(tmp_path), host=host).run("t", run_id=RID)
    assert res.status == "success"
    assert ids_in(tmp_path) == [{"id": "x", "key": "gate"}]  # only the accepted decision is recorded, once


# ================================================================ stack document (P47, P49, P52, P53)

ENV_SCRIPT = ("#!" + sys.executable + "\nimport json, os\nprint(json.dumps(dict(os.environ)))\n")
ROLE_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


def stack_root(tmp, stack=None, name="stack.json", wf=None, man=None):
    root = make_root(tmp, wf=wf, man=man)
    if stack is not None:
        (root / name).write_text(json.dumps(stack))
    return root


def stack_run(tmp, root, **kw):
    return runtime(tmp, root=root, **kw).run("t", run_id=RID)


def test_a_run_with_no_stack_file_runs_with_an_empty_stack(tmp_path):
    host = ort.OrgProcessHost(make_root(tmp_path), session_dir=tmp_path / "s")
    res = runtime(tmp_path, root=tmp_path / "org", host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    assert host.stack == {"bin-env": {}, "roles": {}}


def test_a_valid_stack_is_given_to_the_host_as_a_plain_dict(tmp_path):
    stack = {"bin-env": {"t": {"TDD_WORKTREE": "/w", "TDD_BASE": "main"}},
             "roles": {"t": {"worker": {"tools": ["Read", "Edit"], "workdir": "TDD_WORKTREE"}}},
             "models": {"worker": "whatever"}}  # a key outside the two defined ones is not checked
    root = stack_root(tmp_path, stack)
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "s")
    assert runtime(tmp_path, root=root, host=host).run("t", run_id=RID).status == "success"
    assert host.stack == {"bin-env": stack["bin-env"], "roles": stack["roles"]}
    assert type(host.stack) is dict


@pytest.mark.parametrize("stack,where,reason", [
    ({"roles": {"t": {"worker": {"tools": ["Browse"]}}}}, "roles.t.worker.tools",
     "'Browse' is not one of Read, Grep, Glob, Edit, Write, Bash"),
    ({"roles": {"t": {"worker": {"tools": ["Read", "Read"]}}}}, "roles.t.worker.tools", "'Read' is listed twice"),
    ({"roles": {"t": {"worker": {"tools": "Read"}}}}, "roles.t.worker.tools", "must be a list"),
    ({"roles": {"t": {"worker": {"shell": "yes"}}}}, "roles.t.worker.shell", "unknown key"),
    ({"roles": {"t": {"ghost": {}}}}, "roles.t.ghost", "role is not listed in the manifest"),
    ({"roles": {"nope": {"worker": {}}}}, "roles.nope", "workflow is not listed in the manifest"),
    ({"roles": {"t": {"worker": {"workdir": "TDD_WORKTREE"}}}}, "roles.t.worker.workdir",
     "'TDD_WORKTREE' is not a bin-env variable of this workflow"),
    ({"bin-env": {"t": {"TDD_WORKTREE": "relative"}}, "roles": {"t": {"worker": {"workdir": "TDD_WORKTREE"}}}},
     "roles.t.worker.workdir", "'TDD_WORKTREE' must be an absolute path"),
    ({"bin-env": {"t": {"LD_PRELOAD": "x"}}}, "bin-env.t.LD_PRELOAD", "name is not allowed"),
    ({"bin-env": {"t": {"DYLD_X": "x"}}}, "bin-env.t.DYLD_X", "name is not allowed"),
    ({"bin-env": {"t": {"ORG_ROOT": "x"}}}, "bin-env.t.ORG_ROOT", "name is not allowed"),
    ({"bin-env": {"t": {"PATH": "x"}}}, "bin-env.t.PATH", "name is not allowed"),
    ({"bin-env": {"t": {"lower": "x"}}}, "bin-env.t.lower", "name is not allowed"),
    ({"bin-env": {"t": {"TDD_BASE": 5}}}, "bin-env.t.TDD_BASE", "value must be a string"),
    ({"bin-env": {"t": {"TDD_BASE": "a\u0000b"}}}, "bin-env.t.TDD_BASE", "value must be a string"),
    ({"bin-env": {"nope": {"TDD_BASE": "x"}}}, "bin-env.nope", "workflow is not listed in the manifest"),
    ({"bin-env": ["x"]}, "bin-env", "must be a map"),
])
def test_a_bad_stack_refuses_the_run_with_a_located_message(tmp_path, stack, where, reason):
    host = ScriptedHost()
    res = stack_run(tmp_path, stack_root(tmp_path, stack), host=host)
    assert res.status == "refused" and host.calls == []
    assert res.errors[0] == f"run refused: stack.json: {where}: {reason}"


def test_a_stack_that_is_not_a_map_or_does_not_load_refuses_the_run(tmp_path):
    root = stack_root(tmp_path)
    (root / "stack.json").write_text("[1]")
    assert stack_run(tmp_path, root).errors[0] == "run refused: stack.json: stack: must be a map"
    (root / "stack.json").write_text('{"bin-env": {}, "bin-env": {}}')  # duplicate key: the 2.1 loader refuses it
    res = stack_run(tmp_path, root)
    assert res.status == "refused" and res.errors[0].startswith("run refused: stack.json: ")
    (root / "stack.json").write_text('{"models": NaN}')
    assert stack_run(tmp_path, root).status == "refused"


def test_two_stack_files_refuse_the_run(tmp_path):
    root = stack_root(tmp_path, {}, "stack.json")
    (root / "stack.yaml").write_text("models: {}\n")
    res = stack_run(tmp_path, root)
    assert res.status == "refused" and "stack.json" in res.errors[0] and "stack.yaml" in res.errors[0]


def test_a_yaml_stack_loads(tmp_path):
    yaml = pytest.importorskip("yaml", reason="PyYAML is optional")
    root = stack_root(tmp_path)
    (root / "stack.yaml").write_text(yaml.safe_dump({"bin-env": {"t": {"TDD_BASE": "main"}}}))
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "s")
    assert runtime(tmp_path, root=root, host=host).run("t", run_id=RID).status == "success"
    assert host.stack["bin-env"] == {"t": {"TDD_BASE": "main"}}
    (root / "stack.yaml").write_text("bin-env:\n  t:\n    LD_PRELOAD: x\n")
    res = runtime(tmp_path / "x" if False else tmp_path, root=root, host=ScriptedHost()).run("t", run_id="b" * 32)
    assert res.errors[0] == "run refused: stack.yaml: bin-env.t.LD_PRELOAD: name is not allowed"


def test_the_stack_is_part_of_the_hashed_file_map_and_the_header(tmp_path):
    root = stack_root(tmp_path, {"models": {}})
    assert "stack.json" in ort.build_file_map(root)
    runtime(tmp_path, root=root).run("t", run_id=RID)
    header = LEDGER(tmp_path).read()[0]["body"]
    assert header["stack_hash"] == ort.hashlib.sha256((root / "stack.json").read_bytes()).hexdigest()


def test_r62_a_bin_program_sees_exactly_the_bin_env_names_and_the_runtime_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    monkeypatch.setenv("TDD_TIMEOUT", "99")
    monkeypatch.setenv("TDD_BASE", "from-the-runtime")
    stack = {"bin-env": {"t": {"TDD_BASE": "main", "TDD_TEST_CMD": "pytest -q"}}}
    root = stack_root(tmp_path, stack, wf=doc(("a", leaf())))
    (root / "bin" / "work").write_text(ENV_SCRIPT)
    host = ort.OrgProcessHost(root, session_dir=tmp_path / "s")
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    env = res.output
    assert env["TDD_BASE"] == "main" and env["TDD_TEST_CMD"] == "pytest -q"
    assert "HOME" not in env and "TDD_TIMEOUT" not in env
    assert {"ORG_ROOT", "ORG_RUN", "ORG_KEY", "PATH"} <= set(env)
    assert {k for k in env if k.startswith("TDD_")} == {"TDD_BASE", "TDD_TEST_CMD"}


def test_a_step_cannot_add_environment_beyond_the_stack(tmp_path):
    task = leaf()
    task["run"]["shell"]["environment"] = {"EVIL": "1", "TDD_BASE": "step"}
    root = stack_root(tmp_path, {"bin-env": {"t": {"TDD_BASE": "main"}}}, wf=doc(("a", task)))
    (root / "bin" / "work").write_text(ENV_SCRIPT)
    res = runtime(tmp_path, root=root, host=ort.OrgProcessHost(root, session_dir=tmp_path / "s")).run("t", run_id=RID)
    assert res.status == "success" and res.output["TDD_BASE"] == "main" and "EVIL" not in res.output


def test_names_that_break_the_rules_are_never_forwarded_even_if_a_host_was_handed_them(tmp_path):
    host = ort.OrgProcessHost(make_root(tmp_path), session_dir=tmp_path / "s")
    host.bind_stack({"bin-env": {"t": {"OK_NAME": "1", "LD_PRELOAD": "x", "ORG_RUN": "x", "PATH": "x", "bad": "x"}},
                     "roles": {}}, lambda key: "t")
    assert host._bin_env("a") == {"OK_NAME": "1"}


def test_a_subflow_uses_its_own_workflows_bin_env(tmp_path):
    call = {"run": {"workflow": {"namespace": "org", "name": "u", "version": "1.0.0"}},
            "metadata": {"org": {"by": "code", "role": "worker", "metrics": ["m1"], "acceptance": [{"check": "c"}]}}}
    man = manifest(workflows={"t": {"path": "workflows/t.json", "floors": []},
                              "u": {"path": "workflows/u.json", "floors": []}})
    stack = {"bin-env": {"t": {"TDD_BASE": "from-t"}, "u": {"TDD_VERIFY_CMD": "from-u"}}}
    root = stack_root(tmp_path, stack, wf=doc(("call", call)), man=man)
    (root / "workflows" / "u.json").write_text(json.dumps(doc(("inner", leaf()), name="u")))
    (root / "bin" / "work").write_text(ENV_SCRIPT)
    res = runtime(tmp_path, root=root, host=ort.OrgProcessHost(root, session_dir=tmp_path / "s")).run("t", run_id=RID)
    assert res.status == "success", res.errors
    assert res.output["TDD_VERIFY_CMD"] == "from-u" and "TDD_BASE" not in res.output


# ---- P53: the rung of a stack change is per key


def stack_store(tmp, root):
    return snapshot(tmp, root)


def edit_stack(root, fn, name="stack.json"):
    doc_ = json.loads((root / name).read_text())
    fn(doc_)
    (root / name).write_text(json.dumps(doc_))


BASE_STACK = {"models": {"worker": "m1"}, "bin-env": {"t": {"TDD_TEST_CMD": "pytest -q"}},
              "roles": {"t": {"reviewer": {"tools": ["Read", "Grep", "Glob"]}}}}


def test_a_change_to_a_free_stack_key_is_allowed(tmp_path):
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    edit_stack(root, lambda d: d["models"].update(worker="m2"))
    res = rt_with(tmp_path, root, store, proposer_rungs=("free",)).run("t", run_id=RID)
    assert res.status == "success", res.errors


def test_a_change_to_roles_needs_the_protected_rung(tmp_path):
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    edit_stack(root, lambda d: d["roles"]["t"]["reviewer"]["tools"].append("Bash"))
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.errors[0] == "run refused: stack.json: change needs rung 'protected' and has no owner signature"
    ok = rt_with(tmp_path, root, store, proposer_rungs=("free", "ordinary", "protected")).run("t", run_id="c" * 32)
    assert ok.status == "success", ok.errors


def test_a_change_to_bin_env_needs_the_protected_rung(tmp_path):
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    edit_stack(root, lambda d: d["bin-env"]["t"].update(TDD_TEST_CMD="pytest -q -x"))
    res = rt_with(tmp_path, root, store).run("t", run_id=RID)
    assert res.errors[0] == "run refused: stack.json: change needs rung 'protected' and has no owner signature"


def test_adding_removing_or_emptying_a_protected_key_is_a_protected_change(tmp_path):
    root = stack_root(tmp_path, {"models": {}})
    store = stack_store(tmp_path, root)
    edit_stack(root, lambda d: d.update({"bin-env": {"t": {"TDD_BASE": "main"}}}))
    assert rt_with(tmp_path, root, store).run("t", run_id=RID).status == "refused"
    root2 = stack_root(tmp_path / "two", BASE_STACK) if (tmp_path / "two").mkdir() is None else None
    store2 = snapshot(tmp_path / "two", root2)
    edit_stack(root2, lambda d: d.pop("roles"))
    assert rt_with(tmp_path / "two", root2, store2).run("t", run_id=RID).errors[0].startswith("run refused: stack.json")


def test_deleting_or_adding_the_whole_stack_file_is_classified_by_its_keys(tmp_path):
    root = stack_root(tmp_path, {"models": {}})
    store = stack_store(tmp_path, root)
    (root / "stack.json").unlink()
    assert rt_with(tmp_path, root, store).run("t", run_id=RID).status == "success"  # only a free key was lost
    root_b = stack_root(tmp_path / "b", BASE_STACK) if (tmp_path / "b").mkdir() is None else None
    store_b = snapshot(tmp_path / "b", root_b)
    (root_b / "stack.json").unlink()
    assert rt_with(tmp_path / "b", root_b, store_b).run("t", run_id=RID).status == "refused"


def test_an_unparseable_stack_change_is_frozen(tmp_path):
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    (root / "stack.json").write_text("{not json")
    res = rt_with(tmp_path, root, store, proposer_rungs=("free", "ordinary", "protected")).run("t", run_id=RID)
    assert res.errors[0] == "run refused: stack.json: change needs rung 'frozen' and has no owner signature"


def test_an_unchanged_stack_runs_under_enforcement_and_other_files_still_use_check_change(tmp_path):
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    assert rt_with(tmp_path, root, store).run("t", run_id=RID).status == "success"
    (root / "checks" / "c.py").write_text("import sys\nsys.exit(0)\n# edited\n")
    res = rt_with(tmp_path, root, store).run("t", run_id="d" * 32)
    assert res.errors[0] == "run refused: checks/c.py: change needs rung 'frozen' and has no owner signature"


def test_the_same_stack_in_the_other_format_is_no_change(tmp_path):
    yaml = pytest.importorskip("yaml", reason="PyYAML is optional")
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    (root / "stack.json").unlink()
    (root / "stack.yaml").write_text(yaml.safe_dump(BASE_STACK))
    assert rt_with(tmp_path, root, store, proposer_rungs=("free",)).run("t", run_id=RID).status == "success"


def test_a_change_that_leaves_two_stack_files_is_frozen(tmp_path):
    root = stack_root(tmp_path, BASE_STACK)
    store = stack_store(tmp_path, root)
    (root / "stack.yaml").write_text("models: {}\n")
    res = rt_with(tmp_path, root, store, proposer_rungs=("free", "ordinary", "protected")).run("t", run_id=RID)
    assert res.errors[0] == "run refused: stack.yaml: change needs rung 'frozen' and has no owner signature"
