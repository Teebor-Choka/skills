import pytest
from layout_kit import (CHARTER, ITER, POLICY, PROC, check_agents_dir, commit, git, has, main, make_repo,
                        process_revision, write)


def errs(repo, **kw):
    return check_agents_dir(repo, **kw)


# ---- the whole


def test_a_repo_with_no_agents_directory_is_valid(tmp_path):
    (tmp_path / "plain").mkdir()
    assert errs(tmp_path / "plain") == []


def test_a_complete_layout_is_valid(tmp_path):
    assert errs(make_repo(tmp_path)) == []


def test_only_the_owned_names_are_checked_so_other_tools_keep_their_files(tmp_path):
    repo = make_repo(tmp_path, files={".agents/skills/x/SKILL.md": "not frontmatter at all", ".agents/notes.txt": "x"})
    assert errs(repo) == []


def test_a_path_that_is_not_a_directory_is_an_error(tmp_path):
    assert errs(tmp_path / "missing") != []


# ---- policy.md


def test_a_malformed_policy_is_an_error_naming_the_file(tmp_path):
    repo = make_repo(tmp_path, files={".agents/policy.md": "no frontmatter"})
    assert has(errs(repo), "policy.md")


def test_the_policy_may_name_only_a_procedure_that_exists(tmp_path):
    repo = make_repo(tmp_path, files={".agents/policy.md": "---\nprocedure: ghost\n---\n"})
    assert has(errs(repo), "ghost")


def test_a_policy_with_no_procedure_key_is_valid(tmp_path):
    assert errs(make_repo(tmp_path, files={".agents/policy.md": "---\nmode: team\n---\n"})) == []


# ---- charter.md


@pytest.mark.parametrize("charter, word", [
    ("---\nprocedure: campaign-ops\n---\n", "owner"),
    ("---\nowner: me\n---\n", "owner"),
    ("---\nowner:\n  channel: chat\n---\n", "answer-path"),
    ("---\nowner:\n  answer-path: signed\n---\n", "channel"),
    ("---\nowner:\n  channel: \"  \"\n  answer-path: signed\n---\n", "channel"),
    ("---\nowner:\n  channel: chat\n  answer-path: signed\ntriggers:\n  go: ghost\n---\n", "ghost"),
    ("---\nowner:\n  channel: chat\n  answer-path: signed\nprocedure: ghost\n---\n", "ghost"),
    ("---\nowner:\n  channel: chat\n  answer-path: signed\ntriggers: nope\n---\n", "triggers"),
])
def test_a_charter_must_say_who_the_owner_is_and_name_real_procedures(tmp_path, charter, word):
    assert has(errs(make_repo(tmp_path, files={".agents/charter.md": charter})), word)


@pytest.mark.parametrize("key", ["key", "secret", "token", "password"])
def test_a_charter_may_not_hold_a_secret(tmp_path, key):
    charter = f"---\nowner:\n  channel: chat\n  answer-path: signed\n{key}: abc123\n---\n"
    assert has(errs(make_repo(tmp_path, files={".agents/charter.md": charter})), key)


# ---- procedures/


def test_a_procedure_file_must_be_named_after_its_name_key(tmp_path):
    repo = make_repo(tmp_path, files={".agents/procedures/campaign-ops.md": PROC.replace("name: campaign-ops", "name: other")})
    assert has(errs(repo), "name")


def test_an_invalid_procedure_is_reported_with_its_file_and_the_validator_error(tmp_path):
    bad = PROC.replace("needs: [brief]", "needs: [ghost]")
    errors = errs(make_repo(tmp_path, files={".agents/procedures/campaign-ops.md": bad}))
    assert has(errors, "campaign-ops.md") and has(errors, "ghost")


def test_a_procedure_must_meet_the_metric_and_kpi_rules(tmp_path):
    bad = PROC.replace("    metrics: [briefs-per-week]\n", "", 1)
    assert has(errs(make_repo(tmp_path, files={".agents/procedures/campaign-ops.md": bad})), "metric")


def test_files_that_are_not_markdown_in_procedures_are_ignored(tmp_path):
    assert errs(make_repo(tmp_path, files={".agents/procedures/notes.txt": "x"})) == []


# ---- iterations/


@pytest.mark.parametrize("bad, word", [
    (ITER.replace("  reason: tighten review\n", ""), "reason"),
    (ITER.replace("direction: down", "direction: sideways"), "direction"),
    (ITER.replace("window: 3 stages", "window: soon"), "window"),
    (ITER.replace("touches: [procedures/campaign-ops.md]\n", ""), "touches"),
    (ITER.replace("touches: [procedures/campaign-ops.md]", "touches: [src/main.rs]"), "touches"),
    (ITER.replace("outcome: pending", "outcome: great"), "outcome"),
    (ITER.replace("outcome: pending\n", ""), "outcome"),
])
def test_an_iteration_record_must_say_what_changed_and_what_it_touched(tmp_path, bad, word):
    repo = make_repo(tmp_path, files={".agents/iterations/0001-initial.md": bad})
    assert has(errs(repo), word)


def test_an_iteration_may_carry_the_revision_it_became(tmp_path):
    good = ITER.replace("outcome: pending\n", "outcome: confirmed\nrevision: 0a1b2c3d4e5f\n")
    assert errs(make_repo(tmp_path, files={".agents/iterations/0001-initial.md": good})) == []


def test_a_revision_that_does_not_look_like_a_commit_is_refused(tmp_path):
    bad = ITER.replace("outcome: pending\n", "outcome: confirmed\nrevision: not-a-sha\n")
    assert has(errs(make_repo(tmp_path, files={".agents/iterations/0001-initial.md": bad})), "revision")


def test_an_iteration_number_may_not_be_skipped(tmp_path):
    assert has(errs(make_repo(tmp_path, files={".agents/iterations/0003-skipped.md": ITER})), "0002")


def test_an_iteration_number_may_not_be_used_twice(tmp_path):
    assert has(errs(make_repo(tmp_path, files={".agents/iterations/0001-again.md": ITER})), "0001")


def test_an_iteration_file_must_be_named_with_a_four_digit_number_and_a_slug(tmp_path):
    repo = make_repo(tmp_path, files={".agents/iterations/first.md": ITER})
    assert has(errs(repo), "first.md")


# ---- runs/


def test_the_runs_directory_must_be_ignored_by_git(tmp_path):
    repo = make_repo(tmp_path, ignore_runs=False)
    assert has(errs(repo), "runs")


def test_an_ignored_runs_directory_is_valid_and_its_contents_are_never_read(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, ".agents/runs/r1/procedures/evil.md", "not valid")
    assert errs(repo) == []


def test_a_directory_that_is_not_a_git_repo_skips_the_ignore_check(tmp_path):
    repo = tmp_path / "plain"
    write(repo, ".agents/policy.md", POLICY)
    write(repo, ".agents/procedures/campaign-ops.md", PROC)
    assert not has(errs(repo), "runs")


# ---- the change rule


def base_of(repo):
    return git(repo, "rev-parse", "HEAD")


def test_a_change_to_a_process_document_with_no_iteration_record_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/policy.md", POLICY.replace("single", "team"))
    commit(repo)
    assert has(errs(repo, base=base), "iteration")


def test_the_same_change_with_a_new_iteration_record_is_accepted(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/policy.md", POLICY.replace("single", "team"))
    write(repo, ".agents/iterations/0002-team-mode.md", ITER.replace("procedures/campaign-ops.md", "policy.md"))
    commit(repo)
    assert errs(repo, base=base) == []


@pytest.mark.parametrize("path", [".agents/charter.md", ".agents/procedures/campaign-ops.md"])
def test_each_process_document_needs_its_record(tmp_path, path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    text = CHARTER.replace("chat", "pager") if "charter" in path else PROC.replace("2 rounds", "3 rounds")
    write(repo, path, text)
    commit(repo)
    assert has(errs(repo, base=base), "iteration")


def test_a_change_elsewhere_needs_no_record(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, "src/main.rs", "fn main() {}")
    commit(repo)
    assert errs(repo, base=base) == []


def _rename(repo):
    git(repo, "mv", ".agents/iterations/0001-initial.md", ".agents/iterations/0001-renamed.md")


def _delete(repo):
    git(repo, "rm", "-q", ".agents/iterations/0001-initial.md")


@pytest.mark.parametrize("action", [_rename, _delete], ids=["renamed", "deleted"])
def test_an_iteration_record_may_not_be_deleted_or_renamed(tmp_path, action):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    action(repo)
    commit(repo)
    assert has(errs(repo, base=base), "0001")


def test_an_existing_iteration_record_may_be_updated_when_its_window_closes(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/iterations/0001-initial.md", ITER.replace("outcome: pending", "outcome: confirmed"))
    commit(repo)
    assert errs(repo, base=base) == []


def test_an_unknown_base_ref_is_an_error_not_a_pass(tmp_path):
    assert has(errs(make_repo(tmp_path), base="no-such-ref"), "base")


# ---- the revision a snapshot pins


def test_the_revision_is_the_commit_that_last_changed_the_process_documents(tmp_path):
    repo = make_repo(tmp_path)
    first = process_revision(repo)
    write(repo, "src/main.rs", "fn main() {}")
    commit(repo)
    assert process_revision(repo) == first
    write(repo, ".agents/policy.md", POLICY.replace("single", "team"))
    second = commit(repo)
    assert process_revision(repo) == second != first


def test_adding_an_iteration_record_does_not_move_the_revision(tmp_path):
    repo = make_repo(tmp_path)
    first = process_revision(repo)
    write(repo, ".agents/iterations/0002-x.md", ITER)
    commit(repo)
    assert process_revision(repo) == first


def test_the_revision_is_none_outside_git_or_with_no_process_documents(tmp_path):
    (tmp_path / "plain").mkdir()
    assert process_revision(tmp_path / "plain") is None


# ---- the command


def test_the_cli_exits_one_on_an_error_and_prints_it(tmp_path, capsys):
    repo = make_repo(tmp_path, files={".agents/policy.md": "---\nprocedure: ghost\n---\n"})
    assert main([str(repo)]) == 1 and "ghost" in capsys.readouterr().err


def test_the_cli_exits_zero_on_a_valid_layout_and_takes_a_base(tmp_path):
    repo = make_repo(tmp_path)
    assert main([str(repo)]) == 0 and main([str(repo), "--base", "HEAD"]) == 0


def test_the_new_record_must_cover_every_process_document_that_changed(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/policy.md", POLICY.replace("single", "team"))
    write(repo, ".agents/procedures/campaign-ops.md", PROC.replace("2 rounds", "3 rounds"))
    write(repo, ".agents/iterations/0002-policy-only.md", ITER.replace("procedures/campaign-ops.md", "policy.md"))
    commit(repo)
    errors = errs(repo, base=base)
    assert has(errors, "procedures/campaign-ops.md") and has(errors, "not covered")
    assert not has(errors, "policy.md changed")


def test_a_record_that_covers_each_changed_document_is_accepted(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/policy.md", POLICY.replace("single", "team"))
    write(repo, ".agents/procedures/campaign-ops.md", PROC.replace("2 rounds", "3 rounds"))
    both = ITER.replace("[procedures/campaign-ops.md]", "[policy.md, procedures/campaign-ops.md]")
    write(repo, ".agents/iterations/0002-both.md", both)
    commit(repo)
    assert errs(repo, base=base) == []


def test_two_new_records_together_may_cover_the_change(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/policy.md", POLICY.replace("single", "team"))
    write(repo, ".agents/procedures/campaign-ops.md", PROC.replace("2 rounds", "3 rounds"))
    write(repo, ".agents/iterations/0002-policy.md", ITER.replace("procedures/campaign-ops.md", "policy.md"))
    write(repo, ".agents/iterations/0003-proc.md", ITER)
    commit(repo)
    assert errs(repo, base=base) == []


def test_updating_an_old_record_does_not_count_as_documenting_a_new_change(tmp_path):
    repo = make_repo(tmp_path)
    base = base_of(repo)
    write(repo, ".agents/procedures/campaign-ops.md", PROC.replace("2 rounds", "3 rounds"))
    write(repo, ".agents/iterations/0001-initial.md", ITER.replace("pending", "confirmed"))
    commit(repo)
    assert has(errs(repo, base=base), "iteration")


# ---- audit: the change rule and the validator read what the resolver reads

def _change(tmp_path, extra, **kw):
    repo = make_repo(tmp_path)
    base = git(repo, "rev-parse", "HEAD")
    write(repo, ".agents/policy.md", POLICY + "\n")
    for rel, text in extra.items():
        write(repo, rel, text)
    commit(repo, "change")
    return check_agents_dir(repo, base=base, **kw)


@pytest.mark.parametrize("rel", [".agents/iterations/notes.txt", ".agents/iterations/sub/0009-a.md"])
def test_only_a_top_level_numbered_record_can_cover_a_process_change(tmp_path, rel):
    errs = _change(tmp_path, {rel: "---\ntouches: [policy.md]\n---\n"})
    assert has(errs, "not a valid iteration record"), errs


def test_a_procedure_file_with_an_upper_case_suffix_is_an_error(tmp_path):
    repo = make_repo(tmp_path, files={".agents/procedures/foo.MD": PROC.replace("name: campaign-ops", "name: foo")})
    assert has(check_agents_dir(repo), "lowercase"), check_agents_dir(repo)


def test_a_symlinked_document_is_refused_and_its_content_is_not_echoed(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("---\nSECRET_LINE_WITHOUT_COLON\n---\n")
    repo = make_repo(tmp_path)
    (repo / ".agents" / "iterations" / "0002-x.md").symlink_to(secret)
    errs = check_agents_dir(repo)
    assert has(errs, "symlink") and not has(errs, "SECRET_LINE"), errs


def test_an_oversized_document_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, ".agents/procedures/big.md", "---\nname: big\n---\n" + "x" * (300 * 1024))
    assert has(check_agents_dir(repo), "too large")


def test_a_symlinked_policy_is_refused(tmp_path):
    other = tmp_path / "other.md"
    other.write_text(POLICY)
    repo = make_repo(tmp_path)
    (repo / ".agents" / "policy.md").unlink()
    (repo / ".agents" / "policy.md").symlink_to(other)
    assert has(check_agents_dir(repo), "symlink")


def test_a_change_to_an_upper_case_procedure_file_still_needs_a_record(tmp_path):
    errs = _change(tmp_path, {".agents/procedures/foo.MD": PROC.replace("name: campaign-ops", "name: foo")})
    assert any("foo.MD" in e and "iteration record" in e for e in errs), errs


def test_a_symlinked_iteration_record_covers_nothing(tmp_path):
    repo = make_repo(tmp_path)
    base = git(repo, "rev-parse", "HEAD")
    real = tmp_path / "real.md"
    real.write_text(ITER.replace("procedures/campaign-ops.md", "policy.md"))
    write(repo, ".agents/policy.md", POLICY + "\n")
    (repo / ".agents" / "iterations" / "0002-x.md").symlink_to(real)
    commit(repo, "change")
    errs = check_agents_dir(repo, base=base)
    assert has(errs, "not covered by the 'touches'"), errs


def test_a_charter_delegate_must_be_a_name(tmp_path):
    repo = make_repo(tmp_path, files={".agents/charter.md": CHARTER.replace("procedure:", "delegate: [a, b]\nprocedure:")})
    assert has(check_agents_dir(repo), "delegate")
