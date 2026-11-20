"""Acceptance tests for the org runtime (U13b): ledger, resume, signatures, metrics, rungs, the real-time driver.

All model use is scripted. Tests that need `ssh-keygen` skip with a reason when it is missing; the logic tests use
a fake verifier and always run. The signing helper lives here only: the runtime module has no private-key path.
"""
import copy
import json
import os
import shutil
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
NS = "org-event"
HAVE_SSH = shutil.which("ssh-keygen") is not None
needs_ssh = pytest.mark.skipif(not HAVE_SSH, reason="ssh-keygen is not installed")

# ---------------------------------------------------------------- a small org root on disk

CATALOG = {"m1": {"scope": "node", "unit": "count", "better": "lower", "formula": "f",
                  "collector": "collectors/m1.py", "reads": ["run-ledger"]}}
COLLECTOR = ("import json, os\n"
             "print(json.dumps(len(open(os.environ['ORG_LEDGER']).readlines())))\n")
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
    for d in ("workflows", "collectors", "checks", "briefs", "criteria"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(man or manifest()))
    (root / "metrics.json").write_text(json.dumps(catalog))
    (root / "workflows" / "t.json").write_text(json.dumps(wf or doc(("a", leaf()), ("b", leaf()), ("c", leaf()))))
    (root / "checks" / "c.py").write_text("import sys\nsys.exit(0)\n")
    (root / "briefs" / "x.md").write_text("brief")
    (root / "criteria" / "q.md").write_text("Is it clear?")
    if collector is not None:
        (root / "collectors" / "m1.py").write_text(collector)
    return root


class FakeVerifier:
    """A signature is the text `by:<principal>`. No cryptography: the ring logic is under test."""

    def verify(self, principal, keys, payload, sig):
        return sig == f"by:{principal}" and bool(keys)


def fake_ring(**keys):
    return ort.KeyRing({"owner": ["ssh-ed25519 AAAA owner"], "pm": ["ssh-ed25519 AAAA pm"], **keys},
                       verifier=FakeVerifier())


def runtime(tmp, root=None, host=None, ring=None, **kw):
    root = root or make_root(tmp)
    kw.setdefault("snapshots", ort.UNENFORCED)
    kw.setdefault("frozen", ort.FrozenOutside(None, ()))
    kw.setdefault("collector", lambda *a, **k: 0)
    return ort.OrgRuntime(root, ledger_path=tmp / "run.ledger", ledger_key=b"k" * 32, ring=ring or fake_ring(),
                          host=host or ScriptedHost(), **kw)


def summary(res):
    return (res.status, res.errors, res.statuses, res.accepted)


def ev(task="a", decision="approve", sig="by:owner", run=RID):
    return {"type": "org.owner-decided", "data": {"run": run, "task": task, "decision": decision}, "signature": sig}


# ---------------------------------------------------------------- 1. every event is in the ledger, replay rebuilds state


def test_every_interpreter_event_is_appended_to_the_ledger(tmp_path):
    rt = runtime(tmp_path)
    res = rt.run("t", run_id=RID)
    assert res.status == "success", res.errors
    entries = ort.RunLedger(tmp_path / "run.ledger", b"k" * 32).read()
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
        ort.RunLedger(path, b"k" * 32).read()
    path.write_text("\n".join(lines[:2] + [lines[2].replace("task-start", "task-skip")] + lines[3:]) + "\n")
    with pytest.raises(ort.LedgerError):
        ort.RunLedger(path, b"k" * 32).read()


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

    def run_check(self, name, key, evidence):
        self._tick()
        return super().run_check(name, key, evidence)


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
    entries = ort.RunLedger(tmp_path / "run.ledger", b"k" * 32).read()
    assert not any(e["kind"] == "log" and e["body"]["kind"] == "accept" and e["body"].get("status") == "cancelled"
                   for e in entries), "unwinding after the kill must not write to the ledger"
    live = ScriptedHost(checks=CHECKS)
    resumed = runtime(tmp_path, host=live).resume()
    assert summary(resumed) == summary(base)
    assert len(live.calls) == n - k  # journaled answers are not run again


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
    assert ring.list() == {"owner": ["ssh-ed25519 AAAA owner"], "pm": ["ssh-ed25519 AAAA pm"]}


def test_revoke_removes_the_key():
    ring = fake_ring()
    ring.revoke("ssh-ed25519 AAAA pm")
    assert ring.verify(ev(sig="by:pm"), "pm") is False
    assert ring.verify(ev(sig="by:owner"), "owner") is True


def test_a_ring_refuses_private_key_material():
    private = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    with pytest.raises(ort.OwnerKeyError):
        ort.KeyRing({"owner": [private]}, verifier=FakeVerifier())
    with pytest.raises(ort.OwnerKeyError):
        ort.load_ring("owner ssh-ed25519 AAAA\n" + private)


def test_the_module_has_no_signing_path():
    src = (SCRIPTS / "org_runtime.py").read_text()
    assert '"sign"' not in src and "-Y sign" not in src and "'sign'" not in src


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
    ring.revoke("ssh-ed25519 AAAA owner")
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
    ring.revoke("ssh-ed25519 AAAA owner")
    again = runtime(tmp_path, root=root, host=ScriptedHost(events=[(1, ev("gate"))]), ring=ring).replay()
    assert summary(again) == summary(live)


# real signatures through ssh-keygen -------------------------------------------------


def keygen(tmp, name):
    path = tmp / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
    return path, (tmp / f"{name}.pub").read_text().strip()


def sign_event(event, key_path):
    """The owner's side. Lives in the tests: the runtime holds no signing code."""
    payload = ort.event_payload(event)
    out = subprocess.run(["ssh-keygen", "-Y", "sign", "-q", "-f", str(key_path), "-n", NS], input=payload,
                         capture_output=True, check=True).stdout.decode()
    return {**{k: v for k, v in event.items() if k != "signature"}, "signature": out}


def ssh_ring(tmp):
    owner_key, owner_pub = keygen(tmp, "owner")
    pm_key, pm_pub = keygen(tmp, "pm")
    return ort.KeyRing({"owner": [owner_pub], "pm": [pm_pub]}, verifier=ort.SshKeygenVerifier()), owner_key, pm_key


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
    rows = [e["body"] for e in ort.RunLedger(tmp_path / "run.ledger", b"k" * 32).read() if e["kind"] == "metric"]
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
    rows = [e["body"] for e in ort.RunLedger(tmp_path / "run.ledger", b"k" * 32).read() if e["kind"] == "metric"]
    assert len(rows) == 3 and all("value" not in r and "not implemented" in r["error"] for r in rows)


def test_the_process_collector_reads_the_ledger_and_returns_a_number(tmp_path):
    root = make_root(tmp_path)
    rt = runtime(tmp_path, root=root, collector=ort.ProcessCollector(root))
    assert rt.run("t", run_id=RID).status == "success"
    rows = [e["body"] for e in ort.RunLedger(tmp_path / "run.ledger", b"k" * 32).read() if e["kind"] == "metric"]
    assert all(isinstance(r["value"], int) and r["value"] > 0 for r in rows)


def test_resume_does_not_collect_a_metric_twice(tmp_path):
    seen = []
    rt = runtime(tmp_path, host=KillingHost(3), collector=lambda m, e, k, r, p: seen.append(k) or 1)
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    runtime(tmp_path, collector=lambda m, e, k, r, p: seen.append(k) or 1).resume()
    assert sorted(seen) == ["a", "b", "c"]


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


def snapshot(tmp, root, repo=None, frozen=None, signer="owner", ring=None):
    store = ort.SnapshotStore(tmp / "signed")
    files = ort.build_file_map(root)
    outside = frozen.map() if frozen else {}
    store.add(files, outside, f"by:{signer}")
    return store


def rt_with(tmp, root, store, frozen=None, **kw):
    return runtime(tmp, root=root, snapshots=store, frozen=frozen or ort.FrozenOutside(None, ()), **kw)


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
    store.add(ort.build_file_map(root), {}, "by:pm")  # forged: not the owner's
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


def test_the_default_frozen_list_names_the_grammar_hooks_and_plugin_metadata():
    paths = " ".join(ort.DEFAULT_FROZEN_OUTSIDE)
    assert "scripts" in paths and "plugin.json" in paths and "marketplace.json" in paths and "hooks" in paths


def test_a_frozen_path_with_dot_dot_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ort.FrozenOutside(tmp_path, ("../etc/passwd",))


def test_rungs_are_required_explicitly(tmp_path):
    with pytest.raises(TypeError):
        ort.OrgRuntime(make_root(tmp_path), ledger_path=tmp_path / "l", ledger_key=b"k" * 32, ring=fake_ring(),
                       host=ScriptedHost(), frozen=ort.FrozenOutside(None, ()))


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
    kinds = [e["kind"] for e in ort.RunLedger(tmp_path / "run.ledger", b"k" * 32).read()]
    assert "feed" in kinds


def test_a_closed_feed_with_nothing_waiting_on_a_timer_is_a_deadlock_not_a_hang(tmp_path):
    clock = FakeClock()
    feed = ort.QueueFeed()
    rt = runtime(tmp_path, root=gate_root(tmp_path), clock=clock.now, sleep=clock.sleep)
    res = rt.run("t", run_id=RID, feed=feed)  # the gate's own timer fires after an hour of fake time
    assert res.status == "error" and clock.t >= 3600


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
                              env={"ORG_HARNESS": "scripted", "ORG_HARNESS_SCRIPT": str(script_path)})
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
    script.write_text(json.dumps([{"result": "built"}, {"result": "ok", "verdict": "pass"}]))
    host = ort.OrgProcessHost(root, session_dir=sess, env={"ORG_HARNESS": "scripted", "ORG_HARNESS_SCRIPT": str(script)})
    res = runtime(tmp_path, root=root, host=host).run("t", run_id=RID)
    assert res.status == "success", res.errors
    assert [e["result"] for e in res.events if e["kind"] == "item"] == ["pass"]
