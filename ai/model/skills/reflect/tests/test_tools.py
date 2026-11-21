"""Tests for fixed.py, synthesize.py, drill.py and context-audit.py."""
import json
import os
import subprocess

import pytest

from helpers import asst_text, asst_tool, at, load, tool_result, user_text, write

fixed = load("fixed.py")
synth = load("synthesize.py")
drill = load("drill.py")
audit = load("context-audit.py")


# --- RF-04: FIXED by commit date -----------------------------------------------------

def git(repo, *args, date=None):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "hook.sh").write_text("v1")
    git(tmp_path, "add", "hook.sh")
    git(tmp_path, "commit", "-q", "-m", "add hook", date="2026-02-01T12:00:00Z")
    (tmp_path / "hook.sh").write_text("v2")
    git(tmp_path, "commit", "-q", "-a", "-m", "fix gate matcher", date="2026-03-01T12:00:00Z")
    return tmp_path


def test_finding_last_seen_before_the_fix_commit_is_fixed(repo):
    out = fixed.mark([{"id": "F1", "files": ["hook.sh"], "last_seen": "2026-02-15T00:00:00Z"}],
                     repo)
    assert out[0]["status"] == "FIXED"
    assert out[0]["fix"]["subject"] == "fix gate matcher"


def test_finding_seen_after_the_last_commit_stays_open(repo):
    out = fixed.mark([{"id": "F2", "files": ["hook.sh"], "last_seen": "2026-03-10T00:00:00Z"}],
                     repo)
    assert out[0]["status"] == "OPEN"


def test_a_file_git_does_not_know_is_unknown(repo):
    out = fixed.mark([{"id": "F3", "files": ["nope.sh"], "last_seen": "2026-03-10T00:00:00Z"}],
                     repo)
    assert out[0]["status"] == "UNKNOWN"


def test_a_finding_that_names_no_file_is_unknown(repo):
    assert fixed.mark([{"id": "F4", "last_seen": "2026-01-01T00:00:00Z"}], repo)[0][
        "status"] == "UNKNOWN"


# --- RF-12 / RF-22: synthesis -----------------------------------------------------------

def finding(fid, mechanism, verdict, count=None, basis="full"):
    return {"id": fid, "mechanism": mechanism, "verdict": verdict, "count": count, "basis": basis}


def test_opposite_verdicts_on_one_mechanism_are_flagged():
    out = synth.synthesize([finding("A", "gate-hook", "CONFIRMED", 9),
                            finding("B", "gate-hook", "REFUTED", 0),
                            finding("C", "listing", "CONFIRMED", 4)])
    groups = {g["mechanism"]: g for g in out["groups"]}
    assert groups["gate-hook"]["conflict"] is True
    assert groups["listing"]["conflict"] is False


def test_a_root_cause_claim_on_a_sample_is_not_ranked():
    out = synth.synthesize([finding("A", "m1", "ROOT_CAUSE", 50, basis="top-10 sample"),
                            finding("B", "m2", "ROOT_CAUSE", 5, basis="full")])
    assert [f["id"] for f in out["ranked"]] == ["B"]
    assert out["unranked"] == [{"id": "A", "reason": "root-cause claim without a full count"}]


def test_refuted_findings_are_never_ranked_and_ranking_is_by_count():
    out = synth.synthesize([finding("A", "m1", "CONFIRMED", 3), finding("B", "m2", "CONFIRMED", 8),
                            finding("C", "m3", "REFUTED", 99)])
    assert [f["id"] for f in out["ranked"]] == ["B", "A"]
    assert [f["id"] for f in out["refuted"]] == ["C"]


# --- RF-07: drill-down ---------------------------------------------------------------------

def make_sessions(tmp_path):
    main = write(tmp_path, [user_text("run the build"), asst_text("needle once")], name="s.jsonl")
    sub = tmp_path / "s" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.jsonl").write_text("\n".join(json.dumps(r) for r in [
        asst_text("needle here"), asst_text("needle again"), asst_text("needle thrice")]))
    (sub / "agent-def.jsonl").write_text(json.dumps(asst_text("needle elsewhere")))
    return main


def test_drill_ranks_files_with_most_matches_first(tmp_path):
    make_sessions(tmp_path)
    hits = drill.drill([str(tmp_path)], "needle")
    assert os.path.basename(hits[0]["file"]) == "agent-abc.jsonl"
    assert hits[0]["file_matches"] == 3


def test_drill_agent_limits_to_one_subagent(tmp_path):
    make_sessions(tmp_path)
    hits = drill.drill([str(tmp_path)], "needle", agent="def")
    assert {os.path.basename(h["file"]) for h in hits} == {"agent-def.jsonl"}


def test_drill_never_prints_a_secret(tmp_path):
    write(tmp_path, [asst_text("the password=hunter2 leaked")])
    assert "hunter2" not in json.dumps(drill.drill([str(tmp_path)], "leaked"))


# --- RF-10 / RF-17: input-side audit ---------------------------------------------------------

LISTING = "- alpha: does a\n- plug:beta: does b\n- plug:gamma\n- delta\n"


def audit_rows(call_skill="alpha"):
    return [{"type": "system", "subtype": "init", "tools": ["Bash", "Read", "Skill", "Edit"]},
            {"type": "attachment", "attachment": {"type": "skill_listing", "content": LISTING}},
            asst_tool("Bash", {"command": "ls"}),
            asst_tool("Skill", {"skill": call_skill})]


def test_skill_listing_split_into_described_and_name_only_with_sources(tmp_path):
    r = audit.audit([write(tmp_path, audit_rows())])
    listing = r["sessions"][0]["skill_listing"]
    assert (listing["described"], listing["name_only"]) == (2, 2)
    assert listing["chars"] == len(LISTING)
    assert set(listing["by_source"]) == {"user", "plug"}
    assert listing["by_source"]["plug"] == len("- plug:beta: does b\n- plug:gamma\n")


def test_never_called_tools_are_only_those_offered(tmp_path):
    s = audit.audit([write(tmp_path, audit_rows())])["sessions"][0]
    assert s["tools_never_called"] == ["Edit", "Read"]


def test_without_an_offered_tool_list_never_called_is_unknown(tmp_path):
    rows = [r for r in audit_rows() if r.get("type") != "system"]
    s = audit.audit([write(tmp_path, rows)])["sessions"][0]
    assert s["tools_offered"] is None and s["tools_never_called"] is None


def test_per_skill_invocation_rate_over_sessions_that_were_offered_it(tmp_path):
    a = write(tmp_path, audit_rows("alpha"), name="a.jsonl")
    b = write(tmp_path, audit_rows("zzz"), name="b.jsonl")
    rates = audit.audit([a, b])["skill_rates"]
    assert rates["alpha"] == {"offered": 2, "invoked": 1, "rate": 0.5}
    assert rates["plug:beta"] == {"offered": 2, "invoked": 0, "rate": 0.0}


def test_always_on_files_are_sized(tmp_path):
    f = tmp_path / "AGENTS.md"
    f.write_text("x" * 123)
    r = audit.audit([write(tmp_path, audit_rows())], always_on=[str(f)])
    assert r["always_on"] == [{"path": str(f), "chars": 123}]
