"""Acceptance tests for the organization command line (U19). Model use is scripted, clocks are fake, no network.

Signatures use a fake verifier (`by:<role>`), so no test needs `ssh-keygen`.
"""
import hashlib
import io
import json
import os
import signal
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import interpreter as it  # noqa: E402
import org as org_cli  # noqa: E402
import org_runtime as ort  # noqa: E402
from interpreter import ScriptedHost  # noqa: E402

KEY = b"k" * 32
CATALOG = {"m1": {"scope": "node", "unit": "count", "better": "lower", "formula": "f",
                  "collector": "collectors/m1.py", "reads": ["run-ledger"]}}
ORG = {"by": "code", "role": "worker", "metrics": ["m1"], "acceptance": [{"check": "c"}]}


class FakeVerifier:
    def verify(self, principal, keys, payload, sig, namespace):
        return sig == f"by:{principal}" and bool(keys)


class CountingVerifier(FakeVerifier):
    def __init__(self):
        self.calls = 0

    def verify(self, *a):
        self.calls += 1
        return super().verify(*a)


class Killed(BaseException):
    pass


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


def leaf():
    return {"run": {"shell": {"command": "work", "arguments": []}}, "metadata": {"org": dict(ORG)}}


def emit_task(etype):
    return {"emit": {"event": {"with": {"type": etype, "data": {"subject": "x"}}}}, "metadata": {"org": dict(ORG)}}


def gate_task():
    org = {"by": "human", "role": "worker", "metrics": ["m1"], "acceptance": [{"human": "ok"}]}
    return {"listen": {"to": {"one": {"with": {"type": "org.owner-decided"}}}}, "timeout": {"after": {"hours": 1}},
            "metadata": {"org": org}}


def doc(name, on, *tasks):
    d = {"document": {"dsl": "1.1.0", "namespace": "org", "name": name, "version": "0.1.0"},
         "do": [{n: t} for n, t in tasks]}
    if on:
        d["schedule"] = {"on": {"one": {"with": {"type": on}}}}
    return d


def write_root(tmp, docs):
    root = tmp / "org"
    for d in ("workflows", "collectors", "checks", "briefs", "criteria", "bin"):
        (root / d).mkdir(parents=True, exist_ok=True)
    man = {"owner": "teebor", "namespace": "org", "vetoes": ["v"], "checks": {"c": "shape"},
           "roles": {"worker": {"escalates-to": "owner"}, "improver": {"escalates-to": "owner"}},
           "workflows": {n: {"path": f"workflows/{n}.json", "floors": []} for n in docs}}
    (root / "manifest.json").write_text(json.dumps(man))
    (root / "metrics.json").write_text(json.dumps(CATALOG))
    (root / "stack.json").write_text(json.dumps({"bin-env": {}, "roles": {}}))
    (root / "checks" / "c.py").write_text("import sys\nsys.exit(0)\n")
    (root / "collectors" / "m1.py").write_text("print(1)\n")
    (root / "bin" / "work").write_text("#!/bin/sh\nexit 0\n")
    for n, d in docs.items():
        (root / "workflows" / f"{n}.json").write_text(json.dumps(d))
    return root


def chain_root(tmp):
    return write_root(tmp, {
        "improvement-scan": doc("improvement-scan", "org.scan-requested", ("scan", leaf()),
                                ("file", emit_task("org.work-item-ready"))),
        "sw-development": doc("sw-development", "org.work-item-ready", ("build", leaf())),
    })


def gate_root(tmp):
    return write_root(tmp, {"sw-development": doc("sw-development", "org.work-item-ready", ("build", leaf()),
                                                  ("merge-gate", gate_task()))})


class Org:
    """A prepared state directory, an inbox, and a way to call `main` with captured output."""

    def __init__(self, tmp, root):
        self.tmp, self.root = tmp, root
        self.state, self.inbox = tmp / "state", tmp / "inbox"
        for d in (self.state / "keys", self.inbox, tmp / ".git"):
            d.mkdir(parents=True)
        (self.state / "ledger.key").write_bytes(KEY)
        os.chmod(self.state / "ledger.key", 0o600)
        (self.state / "keys" / "owner.pub").write_text("owner ssh-ed25519 AAAAowner\n")
        self.sign_snapshot()
        self.clock = FakeClock()

    def sign_snapshot(self):
        store = ort.SnapshotStore(self.state / "snapshots")
        files = ort.build_file_map(self.root)
        root_id = hashlib.sha256(os.path.realpath(self.root).encode()).hexdigest()[:32]
        outside = ort.FrozenOutside(self.tmp, ort.DEFAULT_FROZEN_OUTSIDE).map()
        store.add(store.next_event(files, outside, root_id), "by:owner", files, outside)

    def call(self, *argv, host=None, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = org_cli.main(list(argv), host=host or ScriptedHost(), verifier=kw.pop("verifier", None) or FakeVerifier(),
                                clock=self.clock.now, sleep=self.clock.sleep, **kw)
        return code, out.getvalue(), err.getvalue()

    def serve(self, *extra, **kw):
        return self.call("serve", "--root", str(self.root), "--state", str(self.state), "--inbox", str(self.inbox),
                         "--once", *extra, **kw)

    def emit(self, etype, *extra):
        return self.call("emit", "--inbox", str(self.inbox), "--type", etype, *extra)

    def status(self, *extra):
        return self.call("status", "--state", str(self.state), *extra)

    def ledgers(self):
        return sorted((self.state / "ledgers").glob("*.ledger"))

    def names(self):
        return sorted(p.name for p in self.inbox.iterdir())

    def decision(self, run_id, signature="by:owner", id="d-1", name="decision.json", task="merge-gate"):
        ev = {"id": id, "type": "org.owner-decided",
              "data": {"run": run_id, "task": task, "decision": "approve"}}
        if signature:
            ev["signature"] = signature
        (self.inbox / name).write_text(json.dumps(ev))

    def run_id(self):
        (path,) = self.ledgers()
        return ort.RunLedger(path, KEY).read()[0]["body"]["run_id"]


@pytest.fixture
def chain(tmp_path):
    return Org(tmp_path, chain_root(tmp_path))


@pytest.fixture
def gated(tmp_path):
    return Org(tmp_path, gate_root(tmp_path))


# ---------------------------------------------------------------- 1. emit, serve, status


def test_emit_then_serve_once_starts_the_chain_and_status_shows_it(chain):
    code, out, err = chain.emit("org.scan-requested", "--id", "scan-1", "--source", "test")
    assert code == 0, err
    code, out, err = chain.serve()
    assert code == 0, err
    assert len(chain.ledgers()) == 2
    for path in chain.ledgers():
        ledger = ort.RunLedger(path, KEY)
        entries = ledger.read()
        ledger.verify_head(entries)
    assert [n for n in chain.names() if n.endswith(".seen")] and not [n for n in chain.names() if n.endswith(".json")]
    code, text, err = chain.status()
    assert code == 0, err
    assert "improvement-scan" in text and "sw-development" in text and "success" in text
    code, js, err = chain.status("--json")
    assert code == 0, err
    data = json.loads(js)
    assert sorted(p["workflow"] for p in data["pairs"]) == ["improvement-scan", "sw-development"]
    assert all(p["status"] == "success" and p["last"]["kind"] for p in data["pairs"])
    assert data["refusals"] == []


def test_status_only_reads(chain):
    chain.emit("org.scan-requested", "--id", "scan-1")
    chain.serve()

    def snap():
        return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in chain.state.rglob("*") if p.is_file()}

    before = snap()
    assert chain.status()[0] == 0 and chain.status("--json")[0] == 0
    assert snap() == before


def test_status_without_a_state_dir_exits_2(tmp_path):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = org_cli.main(["status", "--state", str(tmp_path / "nope")])
    assert code == 2 and "nope" in err.getvalue()


def test_an_event_nothing_starts_on_is_seen_and_reported(chain):
    chain.emit("org.unknown", "--id", "u-1")
    code, out, err = chain.serve()
    assert code == 0 and chain.ledgers() == [] and "no workflow starts" in out


# ---------------------------------------------------------------- 2. [A] decisions through the inbox


def test_a_signed_decision_arriving_later_completes_the_gate(gated):
    gated.emit("org.work-item-ready", "--id", "w-1")

    def arrive():
        gated.decision(gated.run_id())

    gated.clock.on_sleep.append((30, arrive))
    code, out, err = gated.serve()
    assert code == 0, (out, err)
    assert gated.clock.t < 3600  # woke at the file, not at the one hour timeout
    assert (gated.inbox / "decision.seen").exists()
    status = json.loads(gated.status("--json")[1])
    assert [p["status"] for p in status["pairs"]] == ["success"]


@pytest.mark.parametrize("signature", [None, "by:nobody", "garbage"])
def test_an_unsigned_or_foreign_decision_is_rejected_and_the_gate_times_out(gated, signature):
    gated.emit("org.work-item-ready", "--id", "w-1")
    gated.clock.on_sleep.append((30, lambda: gated.decision(gated.run_id(), signature=signature)))
    code, out, err = gated.serve()
    assert code == 1
    assert (gated.inbox / "decision.rejected").exists() and not (gated.inbox / "decision.seen").exists()
    assert gated.clock.t >= 3600
    status = json.loads(gated.status("--json")[1])
    assert [p["status"] for p in status["pairs"]] == ["error"]


def test_a_decision_signed_for_another_run_stays_in_the_inbox(gated):
    gated.emit("org.work-item-ready", "--id", "w-1")
    gated.clock.on_sleep.append((30, lambda: gated.decision("f" * 32)))
    code, out, err = gated.serve()
    assert code == 1 and (gated.inbox / "decision.json").exists()  # the run timed out; the file was not eaten


# ---------------------------------------------------------------- 3. [A] once only


def test_the_same_event_id_twice_starts_one_run_and_a_restart_does_not_rerun(chain):
    chain.emit("org.scan-requested", "--id", "same")
    chain.emit("org.scan-requested", "--id", "same")
    code, out, err = chain.serve()
    assert code == 0, err
    assert len(chain.ledgers()) == 2 and "duplicate" in out  # scan and the work item it filed
    chain.emit("org.scan-requested", "--id", "same")
    code, out, err = chain.serve()
    assert code == 0 and len(chain.ledgers()) == 2


# ---------------------------------------------------------------- 4. [A] hostile inbox files


def test_hostile_files_are_rejected_and_the_loop_keeps_going(chain):
    inbox = chain.inbox
    good = json.dumps({"id": "g-1", "type": "org.scan-requested"})
    (inbox / "a-reserved.json").write_text(json.dumps({"id": "r-1", "type": "org.owner-decided", "data": {}}))
    (chain.tmp / "outside.json").write_text(good)
    os.symlink(chain.tmp / "outside.json", inbox / "b-link.json")
    os.mkfifo(inbox / "c-fifo.json")
    (inbox / "d-big.json").write_text(json.dumps({"id": "b-1", "type": "x", "pad": "x" * 1_100_000}))
    (inbox / "e-nan.json").write_text('{"id": "n-1", "type": "x", "data": {"v": NaN}}')
    (inbox / "f-deep.json").write_text('{"id": "p-1", "type": "x", "data": ' + "[" * 200 + "]" * 200 + "}")
    (inbox / "g-notobject.json").write_text("[1]")
    (inbox / "z-good.json").write_text(good)
    code, out, err = chain.serve()
    assert code == 0, err
    for stem in ("a-reserved", "b-link", "c-fifo", "d-big", "e-nan", "f-deep", "g-notobject"):
        assert os.path.lexists(inbox / f"{stem}.rejected"), stem
        assert not os.path.lexists(inbox / f"{stem}.json"), stem
    assert (inbox / "z-good.seen").exists()
    assert len(chain.ledgers()) == 2  # the good event still ran
    assert "a-reserved" in err


def test_an_event_the_dispatcher_refuses_is_moved_to_rejected(chain):
    (chain.inbox / "no-id.json").write_text(json.dumps({"type": "org.scan-requested"}))
    code, out, err = chain.serve()
    assert code == 0 and (chain.inbox / "no-id.rejected").exists() and chain.ledgers() == []


# ---------------------------------------------------------------- 5. [A] refusals at start


def test_a_second_serve_on_the_same_state_exits_2(chain):
    fcntl = pytest.importorskip("fcntl")
    with open(chain.state / "serve.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        code, out, err = chain.serve()
    assert code == 2 and "serve.lock" in err
    assert chain.serve()[0] == 0  # released


def refusal(chain, fragment):
    code, out, err = chain.serve()
    assert code == 2 and fragment in err, (code, err)
    assert chain.ledgers() == []


def test_a_short_ledger_key_refuses_to_start(chain):
    (chain.state / "ledger.key").write_bytes(b"k" * 31)
    refusal(chain, "ledger.key")


def test_a_loose_mode_ledger_key_refuses_to_start(chain):
    os.chmod(chain.state / "ledger.key", 0o644)
    refusal(chain, "ledger.key")


def test_a_missing_or_symlinked_ledger_key_refuses_to_start(chain):
    real = chain.tmp / "real.key"
    real.write_bytes(KEY)
    os.chmod(real, 0o600)
    (chain.state / "ledger.key").unlink()
    refusal(chain, "ledger.key")
    os.symlink(real, chain.state / "ledger.key")
    refusal(chain, "ledger.key")


def test_missing_keys_or_snapshots_or_stack_refuse_to_start(chain):
    (chain.state / "keys" / "owner.pub").unlink()
    refusal(chain, "keys")
    (chain.state / "keys" / "owner.pub").write_text("owner ssh-ed25519 AAAAowner\n")
    (chain.root / "stack.json").unlink()
    refusal(chain, "stack")


def test_private_key_material_in_the_ring_refuses_to_start(chain):
    (chain.state / "keys" / "owner.pub").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n")
    refusal(chain, "keys")


def test_a_missing_snapshot_store_refuses_to_start(chain):
    import shutil
    shutil.rmtree(chain.state / "snapshots")
    refusal(chain, "snapshots")


def test_a_missing_root_or_inbox_exits_2(chain):
    code, out, err = chain.call("serve", "--root", str(chain.tmp / "none"), "--state", str(chain.state),
                                "--inbox", str(chain.inbox), "--once")
    assert code == 2 and "none" in err
    code, out, err = chain.call("serve", "--root", str(chain.root), "--state", str(chain.state),
                                "--inbox", str(chain.tmp / "no-inbox"), "--once")
    assert code == 2 and "no-inbox" in err


def test_a_changed_root_without_a_new_snapshot_is_refused_and_exits_2(chain):
    (chain.root / "manifest.json").write_text((chain.root / "manifest.json").read_text().replace("teebor", "mallory"))
    chain.emit("org.scan-requested", "--id", "s-1")
    code, out, err = chain.serve()
    assert code == 2 and "refused" in (out + err)


def test_the_cli_has_no_unenforced_path():
    text = (HERE.parent / "scripts" / "org.py").read_text()
    assert "UNENFORCED" not in text


# ---------------------------------------------------------------- the host is built from the environment only


def test_the_process_host_gets_only_org_variables_and_no_scripted_harness_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ORG_HARNESS", "claude-code")
    monkeypatch.setenv("SECRET_TOKEN", "x")
    monkeypatch.delenv("ORG_TEST_HARNESS", raising=False)
    host = org_cli.build_host(chain_root(tmp_path), tmp_path / "sessions")
    assert isinstance(host, ort.OrgProcessHost)
    assert host.env == {"ORG_HARNESS": "claude-code"}


# ---------------------------------------------------------------- 6. emit


@pytest.mark.parametrize("etype", ["org.owner-decided", "org.task-done", "org.owner-"])
def test_emit_refuses_a_reserved_type(chain, etype):
    code, out, err = chain.emit(etype)
    assert code == 2 and "reserved" in err and chain.names() == []


@pytest.mark.parametrize("data", ["{not json", "[1]", "5", '{"v": NaN}', ""])
def test_emit_refuses_data_that_is_not_a_json_object(chain, data):
    code, out, err = chain.emit("org.scan-requested", "--data", data)
    assert code == 2 and chain.names() == []


def test_emit_refuses_an_empty_type_and_a_missing_inbox(chain):
    assert chain.emit("")[0] == 2
    code, out, err = chain.call("emit", "--inbox", str(chain.tmp / "gone"), "--type", "t")
    assert code == 2 and "gone" in err


def test_emit_writes_one_complete_file_with_a_generated_id(chain):
    code, out, err = chain.emit("org.scan-requested", "--data", '{"k": 1}', "--source", "cli")
    assert code == 0, err
    (name,) = chain.names()
    assert name.endswith(".json") and not name.startswith(".")
    ev = json.loads((chain.inbox / name).read_text())
    assert ev["type"] == "org.scan-requested" and ev["data"] == {"k": 1} and ev["source"] == "cli"
    assert isinstance(ev["id"], str) and ev["id"] and ev["id"] in out
    chain.emit("org.scan-requested")
    ids = {json.loads((chain.inbox / n).read_text())["id"] for n in chain.names()}
    assert len(ids) == 2


# ---------------------------------------------------------------- 7. exit codes and signals


def test_a_failing_run_gives_exit_1_and_every_run_is_still_processed(chain):
    chain.emit("org.scan-requested", "--id", "s-1")
    chain.emit("org.scan-requested", "--id", "s-2")
    host = ScriptedHost(steps={"scan": it.StepOutcome(exit_code=1, error="boom")})
    code, out, err = chain.serve(host=host)
    assert code == 1
    assert len([n for n in chain.names() if n.endswith(".seen")]) == 2
    assert len(chain.ledgers()) == 2  # both scans started, neither reached the work item


def test_sigterm_stops_after_the_current_delivery_and_exits_0(chain):
    chain.emit("org.unknown")
    chain.emit("org.scan-requested", "--id", "s-1")
    chain.emit("org.scan-requested", "--id", "s-2")
    kill = lambda req: os.kill(os.getpid(), signal.SIGTERM) or {}  # noqa: E731
    before = signal.getsignal(signal.SIGTERM)
    code, out, err = chain.serve(host=ScriptedHost(steps={"scan": kill}))
    assert code == 0, err
    assert signal.getsignal(signal.SIGTERM) == before
    assert len(chain.ledgers()) == 2  # the delivery in flight finished (scan, then its work item)
    assert len([n for n in chain.names() if n.endswith(".json")]) == 1  # the second scan was not taken


# ---------------------------------------------------------------- follow-up 1: frozen-outside protection

FROZEN = "agents/operating-model/skills/workflow/scripts/grammar.py"


def frozen_file(o, text="v1"):
    path = o.tmp / FROZEN
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def frozen_org(tmp):
    root = chain_root(tmp)
    (tmp / FROZEN).parent.mkdir(parents=True)
    (tmp / FROZEN).write_text("v1")
    o = Org(tmp, root)  # the snapshot holds the frozen file as it is now
    (tmp / FROZEN).write_text("v2")  # then someone changes it without the owner
    return o


def test_the_repo_defaults_to_the_git_top_level_and_its_frozen_files_reach_the_runtime(tmp_path):
    o = frozen_org(tmp_path)
    o.emit("org.scan-requested", "--id", "s-1")
    code, out, err = o.serve()
    assert code == 2 and "frozen" in (out + err) and o.ledgers() == []  # refused: the runtime saw the change


def test_an_explicit_repo_is_used_instead_of_the_default(tmp_path):
    o = frozen_org(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    o.emit("org.scan-requested", "--id", "s-1")
    code, out, err = o.serve("--repo", str(other))  # no frozen files there: differs from the snapshot's list
    assert code == 2 and "frozen" in (out + err)  # the snapshot named a file the repo lacks


def test_no_repo_and_no_flag_refuses_to_start(tmp_path):
    o = Org(tmp_path, chain_root(tmp_path))
    os.rmdir(tmp_path / ".git")
    code, out, err = o.serve()
    assert code == 2 and "--repo" in err and "--no-outside-check" in err and o.ledgers() == []


def test_the_no_outside_check_flag_runs_with_a_warning_and_is_recorded(tmp_path):
    o = Org(tmp_path, chain_root(tmp_path))
    os.rmdir(tmp_path / ".git")  # without the flag this start is refused
    o.emit("org.scan-requested", "--id", "s-1")
    code, out, err = o.serve("--no-outside-check")
    assert code == 0, (out, err)
    assert "warning" in err.lower() and "outside" in err.lower()
    state = json.loads((o.state / "dispatcher.json").read_text())
    assert state["outside_check"] == "disabled"
    assert "outside" in o.status()[1].lower()
    assert json.loads(o.status("--json")[1])["outside_check"] == "disabled"


def test_a_repo_with_the_flag_is_a_usage_error(tmp_path):
    o = Org(tmp_path, chain_root(tmp_path))
    code, out, err = o.serve("--repo", str(tmp_path), "--no-outside-check")
    assert code == 2


# ---------------------------------------------------------------- follow-up 2: restart safety


def kill_at(o, seconds):
    def die():
        raise Killed()
    o.clock.on_sleep.append((seconds, die))


def killed_gate_run(o):
    o.emit("org.work-item-ready", "--id", "w-1")
    kill_at(o, 5)
    with pytest.raises(Killed):
        o.serve()
    state = json.loads((o.state / "dispatcher.json").read_text())
    assert [p["state"] for p in state["pairs"].values()] == ["starting"]


def test_a_run_left_starting_is_resumed_at_startup(gated):
    killed_gate_run(gated)
    gated.clock = FakeClock()
    gated.clock.on_sleep.append((20, lambda: gated.decision(gated.run_id())))
    host = ScriptedHost()
    code, out, err = gated.serve(host=host)
    assert code == 0, (out, err)
    assert not [c for c in host.calls if c[0] == "step"]  # the journal answered the finished step
    state = json.loads((gated.state / "dispatcher.json").read_text())
    (pair,) = state["pairs"].values()
    assert pair["state"] == "done" and pair["status"] == "success"
    assert len(gated.ledgers()) == 1  # the redelivered event did not start a second run
    assert (gated.inbox / "decision.seen").exists()
    assert not [n for n in gated.names() if n.endswith(".json")]


def test_a_resumed_run_that_ends_in_error_gives_exit_1(gated):
    killed_gate_run(gated)
    gated.clock = FakeClock()
    code, out, err = gated.serve()  # nobody decides: the gate times out
    assert code == 1
    (pair,) = json.loads((gated.state / "dispatcher.json").read_text())["pairs"].values()
    assert pair["state"] == "done" and pair["status"] == "error"


def test_a_ledger_that_does_not_verify_is_reported_and_left(gated):
    killed_gate_run(gated)
    (path,) = gated.ledgers()
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"workflow"', b'"workfloW"', 1))
    tampered = path.read_bytes()
    gated.clock = FakeClock()
    code, out, err = gated.serve()
    assert code == 1 and "not resumed" in (out + err) and path.name in (out + err)
    assert path.read_bytes() == tampered and len(gated.ledgers()) == 1
    (pair,) = json.loads((gated.state / "dispatcher.json").read_text())["pairs"].values()
    assert pair["state"] == "starting"


def test_a_starting_pair_without_a_ledger_is_reported_and_left(gated):
    killed_gate_run(gated)
    for p in gated.state.joinpath("ledgers").glob("*.ledger*"):
        p.unlink()
    gated.clock = FakeClock()
    code, out, err = gated.serve()
    assert code == 1 and "not resumed" in (out + err)
    (pair,) = json.loads((gated.state / "dispatcher.json").read_text())["pairs"].values()
    assert pair["state"] == "starting"


# ---------------------------------------------------------------- follow-up 3: a refused run keeps its reason


def test_a_refused_run_is_done_and_status_prints_the_reason(chain):
    (chain.root / "manifest.json").write_text((chain.root / "manifest.json").read_text().replace("teebor", "mallory"))
    chain.emit("org.scan-requested", "--id", "s-1")
    assert chain.serve()[0] == 2
    (pair,) = json.loads(chain.status("--json")[1])["pairs"]
    assert pair["state"] == "done" and pair["status"] == "refused" and "refused" in pair["reason"]
    assert "reason=" in chain.status()[1] and "run refused" in chain.status()[1]
    chain.emit("org.scan-requested", "--id", "s-1")  # the same id is a duplicate: it starts nothing
    chain.serve()
    assert len(json.loads(chain.status("--json")[1])["pairs"]) == 1


# ---------------------------------------------------------------- follow-up 4: verification is not repeated per poll


def test_a_decision_left_in_the_inbox_is_verified_once_until_it_changes(gated):
    verifier = CountingVerifier()
    gated.emit("org.work-item-ready", "--id", "w-1")
    seen = []
    gated.clock.on_sleep.append((1, lambda: gated.decision("f" * 32, name="other.json")))
    gated.clock.on_sleep.append((50, lambda: seen.append(verifier.calls)))

    def rewrite():
        seen.append(verifier.calls)
        gated.decision("e" * 32, name="other.json", id="d-longer-id-2")

    gated.clock.on_sleep.append((100, rewrite))
    code, out, err = gated.serve(verifier=verifier)
    assert code == 1 and (gated.inbox / "other.json").exists()  # nobody decided this run: it timed out
    assert seen[0] == seen[1]  # 50 polls in between, no new verification
    assert seen[1] < verifier.calls <= seen[1] + 2  # the changed file is verified again, not once per poll


# ---------------------------------------------------------------- limit 2: a resumed run's emits are dispatched


def resumable_root(tmp):
    return write_root(tmp, {
        "improvement-scan": doc("improvement-scan", "org.scan-requested", ("file", emit_task("org.work-item-ready")),
                                ("merge-gate", gate_task())),
        "sw-development": doc("sw-development", "org.work-item-ready", ("build", leaf())),
    })


def crash_after_emit(o, *extra):
    o.emit("org.scan-requested", "--id", "s-1", *extra)
    kill_at(o, 5)
    with pytest.raises(Killed):
        o.serve()
    assert len(o.ledgers()) == 1  # the emit is journaled, nothing downstream started
    o.clock = FakeClock()


def restart_and_decide(o):
    o.clock.on_sleep.append((20, lambda: o.decision(o.run_id())))
    return o.serve()


def pairs(o):
    return json.loads((o.state / "dispatcher.json").read_text())["pairs"]


def test_events_emitted_before_a_crash_start_the_downstream_workflow_once_after_the_resume(tmp_path):
    o = Org(tmp_path, resumable_root(tmp_path))
    crash_after_emit(o)
    code, out, err = restart_and_decide(o)
    assert code == 0, (out, err)
    assert len(o.ledgers()) == 2 and "started sw-development" in out
    by_workflow = {k.partition("\n")[2]: v for k, v in pairs(o).items()}
    assert {v["state"] for v in by_workflow.values()} == {"done"}
    down_key = next(k for k in pairs(o) if k.endswith("\nsw-development"))
    assert down_key.partition("\n")[0].startswith(by_workflow["improvement-scan"]["run_id"] + ":")
    assert by_workflow["sw-development"]["depth"] == 1
    # a second restart changes nothing
    assert o.serve()[0] == 0 and len(o.ledgers()) == 2


def test_a_redelivered_emit_after_the_resume_does_not_dispatch_twice(tmp_path):
    o = Org(tmp_path, resumable_root(tmp_path))
    crash_after_emit(o)
    assert restart_and_decide(o)[0] == 0
    down_event = next(k for k in pairs(o) if k.endswith("\nsw-development")).partition("\n")[0]
    o.emit("org.work-item-ready", "--id", down_event)
    o.emit("org.scan-requested", "--id", "s-1")
    code, out, err = o.serve()
    assert code == 0 and len(o.ledgers()) == 2
    assert not [ln for ln in out.splitlines() if ln.startswith("started")] and out.count("duplicate") == 2


def test_the_chain_bound_holds_across_a_resume(tmp_path):
    o = Org(tmp_path, resumable_root(tmp_path))
    crash_after_emit(o, "--data", '{"chain": 8}')  # the run is at the deepest allowed depth
    code, out, err = restart_and_decide(o)
    assert code == 0, (out, err)
    assert len(o.ledgers()) == 1 and "chain depth 9 exceeds 8" in out  # reported like a normal refusal
    refusals = json.loads(o.status("--json")[1])["refusals"]
    assert [r["reason"] for r in refusals] == ["chain depth 9 exceeds 8"]
    assert [p["state"] for p in pairs(o).values()] == ["done"]


def test_a_same_size_rewrite_inside_one_mtime_tick_is_verified_again(gated):
    verifier = CountingVerifier()
    gated.emit("org.work-item-ready", "--id", "w-1")
    other = gated.inbox / "other.json"
    gated.clock.on_sleep.append((1, lambda: gated.decision("f" * 32, name="other.json")))
    seen = []

    def rewrite():
        seen.append(verifier.calls)
        before = other.stat()
        gated.decision("e" * 32, name="other.json")  # same length, other content
        os.utime(other, ns=(before.st_atime_ns, before.st_mtime_ns))  # the same mtime tick
        assert other.stat().st_size == before.st_size and other.stat().st_mtime_ns == before.st_mtime_ns

    gated.clock.on_sleep.append((50, rewrite))
    gated.clock.on_sleep.append((60, lambda: seen.append(verifier.calls)))  # the gate is still waiting here
    code, out, err = gated.serve(verifier=verifier)
    assert code == 1 and other.exists()
    assert seen[0] < seen[1] <= seen[0] + 2  # re-verified at once, not once per poll
