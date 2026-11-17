import hashlib
import json

import pytest
from resolver_kit import (BOUND, OWNER_CHARTER, SPECIFICS, ResolutionError, agents, commit, env_for, git, has, ok,
                          project, resolve, resolve_main, start_run, write)
from layout_kit import PROC, process_revision

# ---- when there is nothing to do, do nothing


def test_with_no_documents_anywhere_the_tool_does_nothing(tmp_path):
    assert resolve(project(tmp_path, {"README.md": "x"}), environ=env_for(tmp_path)) is None


def test_a_missing_user_directory_is_not_an_error(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path / "nowhere"), "HOME": str(tmp_path / "also-nowhere")}
    assert resolve(project(tmp_path), environ=env) is None


def test_run_output_and_other_tools_files_are_not_process_documents(tmp_path):
    repo = project(tmp_path, agents({"runs/r1/events.jsonl": "{}", "skills/x/SKILL.md": "---\nname: x\n---\n"}))
    assert resolve(repo, environ=env_for(tmp_path, {"skills/y.md": "x"})) is None


def test_a_dot_agents_directory_under_the_user_config_is_not_read(tmp_path):
    env = env_for(tmp_path)
    cfg = tmp_path / "cfg" / ".agents" / "procedures"
    cfg.mkdir(parents=True)
    (cfg / "campaign-ops.md").write_text(PROC)
    assert resolve(project(tmp_path), environ=env) is None


# ---- where each document comes from


def test_a_project_alone_supplies_its_documents(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "policy.md": "---\nprocedure: campaign-ops\n---\n"}))
    got = ok(resolve(repo, environ=env_for(tmp_path)))
    assert got["procedure"] == "campaign-ops" and got["sources"]["procedure"] == "project"


def test_the_user_directory_supplies_a_procedure_when_the_project_has_none(tmp_path):
    env = env_for(tmp_path, {"procedures/campaign-ops.md": PROC})
    got = ok(resolve(project(tmp_path), environ=env))
    assert got["procedure"] == "campaign-ops" and got["sources"]["procedure"] == "user"


def test_the_project_procedure_wins_over_the_users_of_the_same_name(tmp_path):
    mine = PROC.replace("2 rounds", "1 rounds")
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": mine}))
    got = ok(resolve(repo, environ=env_for(tmp_path, {"procedures/campaign-ops.md": PROC})))
    assert got["sources"]["procedure"] == "project" and "1 rounds" in got["procedure_text"]


def test_a_procedure_only_the_user_has_is_still_found_when_the_project_has_others(tmp_path):
    other = PROC.replace("name: campaign-ops", "name: other")
    repo = project(tmp_path, agents({"procedures/other.md": other}))
    got = ok(resolve(repo, environ=env_for(tmp_path, {"procedures/campaign-ops.md": PROC}), name="campaign-ops"))
    assert got["sources"]["procedure"] == "user"


def test_a_project_policy_can_supply_the_specifics_of_a_user_procedure(tmp_path):
    env = env_for(tmp_path, {"procedures/campaign-ops.md": BOUND})
    got = ok(resolve(project(tmp_path, agents({"policy.md": SPECIFICS})), environ=env))
    assert got["bindings"] == {"comms.channel": "slack:#campaigns", "report.sink": "issues"}


def test_policy_layers_per_key_with_the_project_over_the_user(tmp_path):
    user = "---\ncomms:\n  channel: email\nreport:\n  sink: wiki\n---\n"
    mine = "---\nprocedure: campaign-ops\nreport:\n  sink: issues\n---\n"
    env = env_for(tmp_path, {"policy.md": user, "procedures/campaign-ops.md": BOUND})
    got = ok(resolve(project(tmp_path, agents({"policy.md": mine})), environ=env))
    assert got["bindings"] == {"comms.channel": "email", "report.sink": "issues"}
    assert got["sources"]["policy"] == ["user", "project"]


def test_the_project_charter_wins_and_the_users_is_the_fallback(tmp_path):
    mine = "---\nowner:\n  channel: pager\n  answer-path: signed reply\n---\n"
    env = env_for(tmp_path, {"charter.md": OWNER_CHARTER.replace("chat", "pager"), "procedures/campaign-ops.md": PROC})
    assert ok(resolve(project(tmp_path, agents({"charter.md": mine})), environ=env))["sources"]["charter"] == "project"
    assert ok(resolve(project(tmp_path, name="p2"), environ=env))["sources"]["charter"] == "user"


def test_xdg_config_home_is_respected_and_home_config_is_the_default(tmp_path):
    env = env_for(tmp_path, {"procedures/campaign-ops.md": PROC})
    assert ok(resolve(project(tmp_path), environ=env))["sources"]["procedure"] == "user"
    home = tmp_path / "h"
    write(home / ".config" / "agents", "procedures/campaign-ops.md", PROC)
    assert ok(resolve(project(tmp_path, name="p2"), environ={"HOME": str(home)}))["sources"]["procedure"] == "user"


# ---- which procedure runs


def two(tmp_path):
    other = PROC.replace("name: campaign-ops", "name: other")
    return project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "procedures/other.md": other}))


def test_an_explicit_name_wins_over_the_policy_key(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "procedures/other.md": PROC.replace("name: campaign-ops", "name: other"), "policy.md": "---\nprocedure: campaign-ops\n---\n"}))
    assert ok(resolve(repo, environ=env_for(tmp_path), name="other"))["procedure"] == "other"


def test_the_policy_key_chooses_the_procedure(tmp_path):
    repo = two(tmp_path)
    write(repo, ".agents/policy.md", "---\nprocedure: other\n---\n")
    commit(repo)
    assert ok(resolve(repo, environ=env_for(tmp_path)))["procedure"] == "other"


def test_the_charter_chooses_when_the_policy_does_not(tmp_path):
    repo = two(tmp_path)
    write(repo, ".agents/charter.md", OWNER_CHARTER.replace("---\nowner", "---\nprocedure: other\nowner", 1))
    commit(repo)
    assert ok(resolve(repo, environ=env_for(tmp_path)))["procedure"] == "other"


def test_a_single_available_procedure_is_chosen_when_nothing_names_one(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    assert ok(resolve(repo, environ=env_for(tmp_path)))["procedure"] == "campaign-ops"


def test_several_procedures_and_no_choice_is_an_error_naming_them(tmp_path):
    got = resolve(two(tmp_path), environ=env_for(tmp_path))
    assert has(got["errors"], "campaign-ops") and has(got["errors"], "other") and got["procedure"] is None


def test_a_named_procedure_that_does_not_exist_is_an_error(tmp_path):
    got = resolve(two(tmp_path), environ=env_for(tmp_path), name="ghost")
    assert has(got["errors"], "ghost")


def test_policy_and_charter_with_no_procedure_anywhere_leave_nothing_to_run(tmp_path):
    repo = project(tmp_path, agents({"policy.md": "---\nmode: team\n---\n"}))
    got = resolve(repo, environ=env_for(tmp_path))
    assert got is not None and got["procedure"] is None and got["errors"] == []


@pytest.mark.parametrize("bad", ["../x", "A b", "", "a/b", "..", "x.md", "-x", "x" * 200])
def test_a_procedure_name_must_be_a_safe_name_and_no_file_outside_is_read(tmp_path, bad):
    secret = tmp_path / "secret.md"
    secret.write_text(PROC)
    got = resolve(two(tmp_path), environ=env_for(tmp_path), name=bad)
    assert got["procedure"] is None and has(got["errors"], "name") and "secret" not in json.dumps(got)


# ---- what must hold before a run starts


def test_an_invalid_procedure_is_reported_with_its_file_and_the_validator_error(tmp_path):
    bad = PROC.replace("needs: [brief]", "needs: [ghost]")
    got = resolve(project(tmp_path, agents({"procedures/campaign-ops.md": bad})), environ=env_for(tmp_path))
    assert has(got["errors"], "campaign-ops.md") and has(got["errors"], "ghost")


def test_a_procedure_must_meet_the_strict_metric_rules(tmp_path):
    bad = PROC.replace("    metrics: [briefs-per-week]\n", "", 1)
    assert has(resolve(project(tmp_path, agents({"procedures/campaign-ops.md": bad})), environ=env_for(tmp_path))["errors"], "metric")


def test_a_key_the_procedure_needs_and_the_policy_does_not_set_is_an_error(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": BOUND, "policy.md": "---\ncomms:\n  channel: slack\n---\n"}))
    errors = resolve(repo, environ=env_for(tmp_path))["errors"]
    assert has(errors, "report.sink") and has(errors, "campaign-ops") and not has(errors, "comms.channel")


def test_only_the_declared_keys_become_bindings(tmp_path):
    policy = SPECIFICS.replace("---\nprocedure", "---\nunrelated: x\nprocedure", 1)
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": BOUND, "policy.md": policy}))
    assert set(ok(resolve(repo, environ=env_for(tmp_path)))["bindings"]) == {"comms.channel", "report.sink"}


# ---- the revision a run is frozen at


def test_a_clean_project_pins_the_commit_that_last_changed_a_process_document(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    got = ok(resolve(repo, environ=env_for(tmp_path)))
    assert got["revision"] == {"project": process_revision(repo), "user": None, "dirty": False}
    write(repo, "src/main.rs", "fn main() {}")
    commit(repo)
    assert ok(resolve(repo, environ=env_for(tmp_path)))["revision"]["project"] == got["revision"]["project"]


@pytest.mark.parametrize("edit", [
    lambda r: write(r, ".agents/procedures/campaign-ops.md", PROC + "\n"),
    lambda r: write(r, ".agents/procedures/new.md", PROC),
    lambda r: write(r, ".agents/policy.md", "---\nmode: team\n---\n"),
], ids=["edited", "untracked", "new policy"])
def test_uncommitted_process_documents_are_refused_unless_allowed(tmp_path, edit):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    edit(repo)
    got = resolve(repo, environ=env_for(tmp_path), name="campaign-ops")
    assert has(got["errors"], "uncommitted") and got["revision"]["dirty"] is True
    allowed = resolve(repo, environ=env_for(tmp_path), name="campaign-ops", allow_dirty=True)
    assert allowed["errors"] == [] and allowed["revision"]["dirty"] is True


def test_an_unrelated_uncommitted_file_does_not_count(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    write(repo, "notes.txt", "x")
    write(repo, ".agents/runs/r1/events.jsonl", "{}")
    assert ok(resolve(repo, environ=env_for(tmp_path)))["revision"]["dirty"] is False


def test_the_user_revision_is_a_hash_of_the_user_documents_that_were_used(tmp_path):
    env = env_for(tmp_path, {"procedures/campaign-ops.md": PROC})
    first = ok(resolve(project(tmp_path), environ=env))["revision"]["user"]
    assert first and first == ok(resolve(project(tmp_path, name="p2"), environ=env))["revision"]["user"]
    write(tmp_path / "cfg" / "agents", "procedures/campaign-ops.md", PROC + "\n")
    assert ok(resolve(project(tmp_path, name="p3"), environ=env))["revision"]["user"] != first


def test_a_user_document_that_was_not_used_does_not_move_the_user_revision(tmp_path):
    env = env_for(tmp_path, {"procedures/campaign-ops.md": PROC})
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    got = ok(resolve(repo, environ=env))
    assert got["revision"]["user"] is None


def test_a_project_that_is_not_a_git_repo_has_no_project_revision_and_is_not_dirty(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}), git_repo=False)
    got = ok(resolve(repo, environ=env_for(tmp_path)))
    assert got["revision"] == {"project": None, "user": None, "dirty": False}


# ---- a cloned repo may not override what the user locked down


def lock(tmp_path, files):
    return env_for(tmp_path, {"procedures/campaign-ops.md": PROC, **files})


def test_a_project_cannot_change_a_value_the_user_locked(tmp_path):
    env = lock(tmp_path, {"policy.md": "---\nmode: team\nlocked: [mode]\n---\n"})
    repo = project(tmp_path, agents({"policy.md": "---\nmode: single\n---\n"}))
    got = resolve(repo, environ=env)
    assert has(got["errors"], "mode") and has(got["errors"], "locked")


def test_a_project_may_restate_a_locked_value_or_leave_it_out(tmp_path):
    env = lock(tmp_path, {"policy.md": "---\nmode: team\nlocked: [mode]\n---\n"})
    same = project(tmp_path, agents({"policy.md": "---\nmode: team\n---\n"}))
    assert ok(resolve(same, environ=env))["policy"]["mode"] == "team"
    assert ok(resolve(project(tmp_path, name="p2"), environ=env))["policy"]["mode"] == "team"


def test_a_locked_dotted_key_reads_through_nested_maps(tmp_path):
    env = lock(tmp_path, {"policy.md": "---\nvcs:\n  remote: origin\nlocked: [vcs.remote]\n---\n"})
    repo = project(tmp_path, agents({"policy.md": "---\nvcs:\n  remote: evil\n---\n"}))
    assert has(resolve(repo, environ=env)["errors"], "vcs.remote")


def test_only_the_users_policy_can_lock_a_key(tmp_path):
    repo = project(tmp_path, agents({"policy.md": "---\nmode: single\nlocked: []\n---\n"}))
    env = lock(tmp_path, {"policy.md": "---\nmode: team\nlocked: [mode]\n---\n"})
    assert has(resolve(repo, environ=env)["errors"], "mode")


def test_a_project_procedure_that_weakens_the_users_is_refused(tmp_path):
    user = PROC.replace("  create:\n    needs: [brief]\n", "  create:\n    floor: true\n    needs: [brief]\n", 1)
    mine = PROC.replace("  create:\n    needs: [brief]\n    consumes: [audience-brief]\n", "  create:\n    needs: []\n    consumes: [audience-brief]\n", 1)
    env = env_for(tmp_path, {"procedures/campaign-ops.md": user})
    got = resolve(project(tmp_path, agents({"procedures/campaign-ops.md": mine})), environ=env)
    assert has(got["errors"], "create") and has(got["errors"], "user")


def test_a_project_procedure_that_keeps_the_users_floor_is_accepted(tmp_path):
    user = PROC.replace("  create:\n    needs: [brief]\n", "  create:\n    floor: true\n    needs: [brief]\n", 1)
    mine = user.replace("2 rounds", "1 rounds")
    env = env_for(tmp_path, {"procedures/campaign-ops.md": user})
    assert ok(resolve(project(tmp_path, agents({"procedures/campaign-ops.md": mine})), environ=env))["sources"]["procedure"] == "project"


def test_a_project_charter_cannot_redirect_the_users_owner(tmp_path):
    env = env_for(tmp_path, {"charter.md": OWNER_CHARTER, "procedures/campaign-ops.md": PROC})
    evil = OWNER_CHARTER.replace("chat", "attacker-webhook")
    got = resolve(project(tmp_path, agents({"charter.md": evil})), environ=env)
    assert has(got["errors"], "owner")
    same = project(tmp_path, agents({"charter.md": OWNER_CHARTER}), name="p2")
    assert ok(resolve(same, environ=env))["charter"]["owner"]["channel"] == "chat"


# ---- the documents themselves


@pytest.mark.parametrize("rel", ["policy.md", "charter.md", "procedures/campaign-ops.md"])
def test_a_symlinked_document_is_refused(tmp_path, rel):
    target = tmp_path / "elsewhere.md"
    target.write_text(PROC if "procedures" in rel else "---\nmode: single\n---\n")
    repo = project(tmp_path, agents({"procedures/other.md": PROC.replace("name: campaign-ops", "name: other")}))
    link = repo / ".agents" / rel
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    commit(repo)
    got = resolve(repo, environ=env_for(tmp_path), name="campaign-ops" if "procedures" in rel else "other")
    assert has(got["errors"], "symlink")


def test_a_user_symlinked_document_is_followed(tmp_path):
    env = env_for(tmp_path)
    real = tmp_path / "real.md"
    real.write_text(PROC)
    folder = tmp_path / "cfg" / "agents" / "procedures"
    folder.mkdir(parents=True)
    (folder / "campaign-ops.md").symlink_to(real)
    assert ok(resolve(project(tmp_path), environ=env))["procedure"] == "campaign-ops"


def test_an_oversized_document_is_refused(tmp_path):
    huge = "---\nmode: single\n---\n" + "x" * 300_000
    got = resolve(project(tmp_path, agents({"policy.md": huge, "procedures/campaign-ops.md": PROC})), environ=env_for(tmp_path))
    assert has(got["errors"], "policy.md") and has(got["errors"], "large")


def test_a_binary_document_is_an_error_not_a_crash(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    (repo / ".agents" / "policy.md").write_bytes(b"\xff\xfe\x00bad")
    commit(repo)
    assert has(resolve(repo, environ=env_for(tmp_path))["errors"], "policy.md")


# ---- starting a run


def test_start_run_freezes_the_resolved_documents_into_a_run(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": BOUND, "policy.md": SPECIFICS}))
    state = start_run(repo, environ=env_for(tmp_path), run_id="r1")
    assert state["run_id"] == "r1" and state["status"] == "new"
    assert state["bindings"] == {"comms.channel": "slack:#campaigns", "report.sink": "issues"}
    assert state["revision"]["project"] and state["resolution"]["sources"]["procedure"] == "project"
    json.dumps(state)


def test_start_run_does_nothing_when_there_is_nothing_to_run(tmp_path):
    assert start_run(project(tmp_path), environ=env_for(tmp_path)) is None
    assert start_run(project(tmp_path, agents({"policy.md": "---\nmode: team\n---\n"}), name="p2"), environ=env_for(tmp_path)) is None


def test_start_run_refuses_documents_with_errors(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": BOUND}))
    with pytest.raises(ResolutionError) as exc:
        start_run(repo, environ=env_for(tmp_path))
    assert has(exc.value.errors, "comms.channel")


def test_start_run_generates_a_distinct_run_id_when_none_is_given(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    ids = {start_run(repo, environ=env_for(tmp_path))["run_id"] for _ in range(5)}
    assert len(ids) == 5 and all(len(i) >= 12 for i in ids)


def test_start_run_turns_the_policy_values_the_runtime_checks_into_numbers(tmp_path):
    policy = "---\nmax-agents: 3\nmax-depth: 2\nregression-threshold: 0.25\nsafety-metrics: [escalations]\n---\n"
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "policy.md": policy}))
    state = start_run(repo, environ=env_for(tmp_path))
    assert state["policy"] == {"max-agents": 3, "max-depth": 2, "regression-threshold": 0.25, "safety-metrics": ["escalations"]}


@pytest.mark.parametrize("policy, word", [
    ("max-agents: many", "max-agents"), ("max-agents: -1", "max-agents"), ("max-depth: 1.5", "max-depth"),
    ("regression-threshold: high", "regression-threshold"), ("regression-threshold: nan", "regression-threshold"),
    ("safety-metrics: [nothing-observes-this]", "safety-metrics"),
])
def test_a_policy_value_the_runtime_cannot_use_is_an_error(tmp_path, policy, word):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "policy.md": f"---\n{policy}\n---\n"}))
    with pytest.raises(ResolutionError) as exc:
        start_run(repo, environ=env_for(tmp_path))
    assert has(exc.value.errors, word)


def test_a_signed_run_can_be_asked_for_and_needs_entities(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    with pytest.raises(ResolutionError) as exc:
        start_run(repo, environ=env_for(tmp_path), trust="signed")
    assert has(exc.value.errors, "entities")


# ---- the command


def run_cli(tmp_path, repo, *extra, monkeypatch=None, env=None):
    for k, v in (env or env_for(tmp_path)).items():
        monkeypatch.setenv(k, v)
    return resolve_main([str(repo), *extra])


def test_the_command_says_so_and_exits_zero_when_there_is_nothing_to_do(tmp_path, monkeypatch, capsys):
    assert run_cli(tmp_path, project(tmp_path), monkeypatch=monkeypatch) == 0
    assert "no process documents" in capsys.readouterr().out


def test_the_command_prints_the_resolution_without_the_policy_or_the_text(tmp_path, monkeypatch, capsys):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": BOUND, "policy.md": SPECIFICS}))
    assert run_cli(tmp_path, repo, monkeypatch=monkeypatch) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["procedure"] == "campaign-ops" and out["bindings"]["report.sink"] == "issues"
    assert "procedure_text" not in out and "policy" not in out and out["errors"] == []


def test_the_command_exits_one_and_prints_each_error(tmp_path, monkeypatch, capsys):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": BOUND}))
    assert run_cli(tmp_path, repo, monkeypatch=monkeypatch) == 1
    assert "comms.channel" in capsys.readouterr().err


def test_the_command_takes_a_procedure_name_and_allows_a_dirty_tree_on_request(tmp_path, monkeypatch, capsys):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    write(repo, ".agents/procedures/campaign-ops.md", PROC + "\n")
    assert run_cli(tmp_path, repo, "--procedure", "campaign-ops", monkeypatch=monkeypatch) == 1
    assert run_cli(tmp_path, repo, "--procedure", "campaign-ops", "--allow-dirty", monkeypatch=monkeypatch) == 0


def test_a_project_cannot_replace_the_users_lock_list_with_its_own(tmp_path):
    repo = project(tmp_path, agents({"policy.md": "---\nmode: single\nlocked: [something-else]\n---\n"}))
    env = lock(tmp_path, {"policy.md": "---\nmode: team\nlocked: [mode]\n---\n"})
    assert has(resolve(repo, environ=env)["errors"], "mode")


def test_the_policy_names_the_procedure_before_the_charter_does(tmp_path):
    repo = two(tmp_path)
    write(repo, ".agents/policy.md", "---\nprocedure: other\n---\n")
    write(repo, ".agents/charter.md", OWNER_CHARTER.replace("---\nowner", "---\nprocedure: campaign-ops\nowner", 1))
    commit(repo)
    assert ok(resolve(repo, environ=env_for(tmp_path)))["procedure"] == "other"


# ---- review findings: the guards hold against omission, renaming, and odd input

FLOORED = PROC.replace("  create:\n", "  create:\n    floor: true\n", 1)


def _vs_user(tmp_path, project_files, user_files, **kw):
    repo = project(tmp_path, agents(project_files))
    return resolve(repo, environ=env_for(tmp_path, user_files), **kw)


def test_a_project_procedure_cannot_strip_a_floor_stage_by_leaving_its_keys_out(tmp_path):
    stripped = FLOORED.replace("    floor: true\n", "", 1)
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": stripped}, {"procedures/campaign-ops.md": FLOORED})
    assert any("floor" in e for e in got["errors"]), got["errors"]


def test_a_project_procedure_cannot_drop_the_review_angles_of_a_floor_stage(tmp_path):
    bare = FLOORED.replace("    review: [brand]\n", "", 1)
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": bare}, {"procedures/campaign-ops.md": FLOORED})
    assert any("review" in e for e in got["errors"]), got["errors"]


def test_a_project_procedure_cannot_rewire_a_stage_around_a_floor_stage(tmp_path):
    rewired = FLOORED.replace("  launch:\n    needs: [create]", "  launch:\n    needs: [brief]", 1)
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": rewired}, {"procedures/campaign-ops.md": FLOORED})
    assert any("floor" in e for e in got["errors"]), got["errors"]


def test_a_project_cannot_dodge_the_user_floor_by_naming_another_procedure(tmp_path):
    evil = PROC.replace("name: campaign-ops", "name: evil")
    got = _vs_user(tmp_path, {"procedures/evil.md": evil, "policy.md": "---\nprocedure: evil\n---\n"},
                   {"procedures/campaign-ops.md": FLOORED, "policy.md": "---\nprocedure: campaign-ops\n---\n"})
    assert any("floor" in e for e in got["errors"]), got["errors"]


@pytest.mark.parametrize("locked", ["mode", "true", "[mode, 3]"])
def test_a_malformed_lock_is_an_error_not_a_crash_or_a_silent_pass(tmp_path, locked):
    got = _vs_user(tmp_path, {"policy.md": "---\nmode: single\n---\n"},
                   {"procedures/campaign-ops.md": PROC, "policy.md": f"---\nmode: team\nlocked: {locked}\n---\n"})
    assert any("locked" in e for e in got["errors"]), got["errors"]


def test_a_project_cannot_set_a_locked_key_the_user_left_unset(tmp_path):
    got = _vs_user(tmp_path, {"policy.md": "---\nmode: team\n---\n"},
                   {"procedures/campaign-ops.md": PROC, "policy.md": "---\nlocked: [mode]\n---\n"})
    assert any("mode" in e for e in got["errors"]), got["errors"]


def test_a_scalar_over_a_map_with_a_locked_path_is_an_error(tmp_path):
    got = _vs_user(tmp_path, {"policy.md": "---\nvcs: anything\n---\n"},
                   {"procedures/campaign-ops.md": PROC, "policy.md": "---\nvcs:\n  remote: x\nlocked: [vcs.remote]\n---\n"})
    assert any("vcs.remote" in e for e in got["errors"]), got["errors"]


def test_a_sibling_overlay_cannot_erase_a_deep_locked_key(tmp_path):
    got = _vs_user(tmp_path, {"policy.md": "---\na:\n  b:\n    d: y\n---\n"},
                   {"procedures/campaign-ops.md": PROC, "policy.md": "---\na:\n  b:\n    c: x\nlocked: [a.b.c]\n---\n"})
    assert any("a.b.c" in e for e in got["errors"]), got["errors"]


def test_a_symlinked_procedures_directory_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "campaign-ops.md").write_text(PROC)
    repo = project(tmp_path, agents({"policy.md": "---\nmode: single\n---\n"}))
    (repo / ".agents" / "procedures").symlink_to(outside)
    got = resolve(repo, environ=env_for(tmp_path), allow_dirty=True)
    assert got["procedure"] is None and any("symlink" in e for e in got["errors"]), got


def test_a_failing_git_status_does_not_pass_as_a_clean_tree(tmp_path, monkeypatch):
    import resolver
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    real = resolver._git
    monkeypatch.setattr(resolver, "_git", lambda r, *a: None if a[0] == "ls-tree" else real(r, *a))
    got = resolve(repo, environ=env_for(tmp_path))
    assert any("git" in e for e in got["errors"]), got["errors"]


def test_a_huge_number_in_policy_is_an_error_not_a_crash(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "policy.md": f"---\nmax-agents: {'9' * 5000}\n---\n"}))
    with pytest.raises(ResolutionError):
        start_run(repo, environ=env_for(tmp_path))


def test_git_runs_without_the_repos_own_hooks_or_fsmonitor(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    marker = tmp_path / "ran"
    hook = tmp_path / "hook.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    git(repo, "config", "core.fsmonitor", str(hook))
    resolve(repo, environ=env_for(tmp_path))
    assert not marker.exists()


def test_an_invalid_user_procedure_is_reported_when_a_project_one_overrides_it(tmp_path):
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": PROC},
                   {"procedures/campaign-ops.md": PROC.replace("needs: [create]", "needs: [ghost]")})
    assert any("<user>" in e for e in got["errors"]), got["errors"]


# ---- inline documents: a parent hands the worker its process documents directly

def _inline(**docs):
    return docs


def test_inline_documents_alone_define_a_run(tmp_path):
    repo = project(tmp_path)
    got = resolve(repo, environ=env_for(tmp_path), inline=_inline(procedures={"campaign-ops": PROC}, policy="---\nmode: single\n---\n"))
    assert got["errors"] == [] and got["procedure"] == "campaign-ops" and got["sources"]["procedure"] == "inline"
    assert got["policy"]["mode"] == "single"


def test_inline_policy_wins_over_the_project_and_the_user(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC, "policy.md": "---\nmode: team\n---\n"}))
    env = env_for(tmp_path, {"policy.md": "---\nmode: single\nmax-agents: 9\n---\n"})
    got = resolve(repo, environ=env, inline=_inline(policy="---\nmode: single\n---\n"))
    assert got["policy"]["mode"] == "single" and got["policy"]["max-agents"] == "9"
    assert got["sources"]["policy"] == ["user", "project", "inline"]


def test_inline_procedure_wins_but_cannot_weaken_the_users_floor(tmp_path):
    repo = project(tmp_path)
    env = env_for(tmp_path, {"procedures/campaign-ops.md": FLOORED})
    stripped = FLOORED.replace("    floor: true\n", "", 1)
    got = resolve(repo, environ=env, inline=_inline(procedures={"campaign-ops": stripped}))
    assert any("floor" in e for e in got["errors"]), got["errors"]


def test_inline_cannot_override_a_locked_policy_key(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    env = env_for(tmp_path, {"policy.md": "---\nmode: team\nlocked: [mode]\n---\n"})
    got = resolve(repo, environ=env, inline=_inline(policy="---\nmode: single\n---\n"))
    assert any("mode" in e for e in got["errors"]), got["errors"]


def test_inline_charter_cannot_redirect_the_owner(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    env = env_for(tmp_path, {"charter.md": OWNER_CHARTER})
    other = "---\nowner:\n  channel: elsewhere\n  answer-path: x\n---\n"
    got = resolve(repo, environ=env, inline=_inline(charter=other))
    assert any("owner" in e for e in got["errors"]), got["errors"]


def test_inline_documents_are_pinned_by_hash_and_never_dirty(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    one = resolve(repo, environ=env_for(tmp_path), inline=_inline(policy="---\nmode: single\n---\n"))
    two = resolve(repo, environ=env_for(tmp_path), inline=_inline(policy="---\nmode: team\n---\n"))
    assert one["revision"]["inline"] and one["revision"]["inline"] != two["revision"]["inline"]
    assert resolve(repo, environ=env_for(tmp_path))["revision"].get("inline") is None


@pytest.mark.parametrize("bad", [{"policy": 3}, {"procedures": []}, {"procedures": {"Bad Name": "x"}}, {"nope": "x"}, {"policy": "x" * 300000}])
def test_malformed_inline_input_is_an_error_not_a_crash(tmp_path, bad):
    got = resolve(project(tmp_path), environ=env_for(tmp_path), inline=bad)
    assert got["errors"], got


def test_the_cli_reads_inline_documents_from_a_json_file(tmp_path, capsys):
    repo = project(tmp_path)
    path = tmp_path / "inline.json"
    path.write_text(json.dumps({"procedures": {"campaign-ops": PROC}, "policy": "---\nmode: single\n---\n"}))
    assert resolve_main([str(repo), "--inline", str(path)]) == 0
    assert "campaign-ops" in capsys.readouterr().out


def test_start_run_freezes_inline_documents(tmp_path):
    state = start_run(project(tmp_path), environ=env_for(tmp_path), inline=_inline(procedures={"campaign-ops": PROC}))
    assert state["resolution"]["sources"]["procedure"] == "inline"


# ---- second review: more ways a higher layer got past a guard

NAMED = lambda n, text=PROC: text.replace("name: campaign-ops", f"name: {n}")  # noqa: E731
USER_OWNER = {"charter.md": OWNER_CHARTER}


@pytest.mark.parametrize("where", ["project", "inline"])
def test_an_empty_charter_cannot_drop_the_users_owner(tmp_path, where):
    proj = {"procedures/campaign-ops.md": PROC}
    kw = {}
    if where == "project":
        proj["charter.md"] = "---\n---\n"
    else:
        kw["inline"] = {"charter": "---\n---\n"}
    got = _vs_user(tmp_path, proj, USER_OWNER, **kw)
    assert any("owner" in e for e in got["errors"]), got["errors"]


def test_a_user_charter_whose_owner_is_not_a_map_is_an_error(tmp_path):
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": PROC}, {"charter.md": "---\nowner: me\n---\n"})
    assert any("owner" in e and "<user>" in e for e in got["errors"]), got["errors"]


def test_a_procedure_that_fails_validation_never_reaches_the_override_guard(tmp_path):
    bad = FLOORED.replace("    needs: [create]", "    needs: true", 1)
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": bad}, {"procedures/campaign-ops.md": FLOORED})
    assert got["errors"]


@pytest.mark.parametrize("text", ["\ud800", "ok\udfff"])
def test_inline_text_that_is_not_valid_unicode_is_an_error_not_a_crash(tmp_path, text):
    got = resolve(project(tmp_path), environ=env_for(tmp_path), inline={"policy": text})
    assert got["errors"], got


def test_with_several_user_procedures_and_none_named_a_new_project_procedure_is_refused(tmp_path):
    user = {"procedures/ship.md": NAMED("ship", FLOORED), "procedures/hotfix.md": NAMED("hotfix", FLOORED)}
    got = _vs_user(tmp_path, {"procedures/yolo.md": NAMED("yolo"), "policy.md": "---\nprocedure: yolo\n---\n"}, user)
    assert got["errors"], got


def test_a_project_cannot_swap_in_a_floorless_user_procedure_for_the_one_the_user_runs(tmp_path):
    user = {"procedures/ship.md": NAMED("ship", FLOORED), "procedures/notes.md": NAMED("notes"),
            "policy.md": "---\nprocedure: ship\n---\n"}
    got = _vs_user(tmp_path, {"procedures/notes.md": NAMED("notes"), "policy.md": "---\nprocedure: notes\n---\n"}, user)
    assert any("floor" in e for e in got["errors"]), got["errors"]


def test_an_inline_procedure_with_a_new_name_still_meets_the_projects_floor(tmp_path):
    proj = {"procedures/ship.md": NAMED("ship", FLOORED), "policy.md": "---\nprocedure: ship\n---\n"}
    got = _vs_user(tmp_path, proj, {}, inline={"procedures": {"yolo": NAMED("yolo")}, "policy": "---\nprocedure: yolo\n---\n"})
    assert any("floor" in e for e in got["errors"]), got["errors"]


@pytest.mark.parametrize("policy", [
    "---\nramble:\n  mode: team\n---\n",
    "---\nfiles:\n  \"*\":\n    mode: team\n---\n",
])
def test_a_lock_also_holds_against_per_skill_and_per_file_overrides(tmp_path, policy):
    got = _vs_user(tmp_path, {"policy.md": policy, "procedures/campaign-ops.md": PROC},
                   {"policy.md": "---\nmode: single\nlocked: [mode]\n---\n"})
    assert any("mode" in e for e in got["errors"]), got["errors"]


def test_git_does_not_run_a_clean_filter_from_the_projects_own_config(tmp_path):
    repo = project(tmp_path, agents({"procedures/campaign-ops.md": PROC}))
    marker = tmp_path / "ran"
    hook = tmp_path / "filter.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\ncat\n")
    hook.chmod(0o755)
    write(repo, ".gitattributes", "*.md filter=evil\n")
    git(repo, "config", "filter.evil.clean", str(hook))
    doc = repo / ".agents" / "procedures" / "campaign-ops.md"
    doc.write_text(PROC)  # a fresh stat: git would re-hash it
    resolve(repo, environ=env_for(tmp_path), allow_dirty=True)
    assert not marker.exists()


def test_process_documents_that_git_ignores_are_not_read_as_clean(tmp_path):
    repo = project(tmp_path, agents({"policy.md": "---\nmode: single\n---\n"}))
    write(repo, ".gitignore", ".agents/runs/\n.agents/procedures/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore")
    write(repo, ".agents/procedures/campaign-ops.md", PROC)
    got = resolve(repo, environ=env_for(tmp_path))
    assert has(got["errors"], "uncommitted"), got["errors"]


def test_a_floor_stage_keeps_its_failure_route(tmp_path):
    base = PROC.replace("  launch:\n", "  launch:\n    floor: true\n", 1)
    other = base.replace("    on-fail:\n      to: create\n      bound: 2 rounds\n", "", 1)
    assert other != base
    got = _vs_user(tmp_path, {"procedures/campaign-ops.md": other}, {"procedures/campaign-ops.md": base})
    assert any("on-fail" in e for e in got["errors"]), got["errors"]


def test_inline_input_is_capped_in_count_and_in_file_size(tmp_path, capsys):
    many = {f"p{i}": PROC for i in range(200)}
    got = resolve(project(tmp_path), environ=env_for(tmp_path), inline={"procedures": many})
    assert any("at most" in e and "procedures" in e for e in got["errors"]), got["errors"]
    big = tmp_path / "big.json"
    big.write_text('{"policy": "' + "x" * (4 * 1024 * 1024) + '"}')
    assert resolve_main([str(project(tmp_path, name="p2")), "--inline", str(big)]) == 1
    assert "too large" in capsys.readouterr().err
