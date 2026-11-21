#!/usr/bin/env bats
# shellcheck disable=SC2030,SC2031 # each @test runs in its own subshell by design
# End-to-end: the hook maps a pending command to a boundary, asks the forge binding for state,
# and blocks only when the condition is genuinely unmet. This is the issue's acceptance:
# a green+reviewed merge passes with no SWE_GATE_OK; a red/unreviewed merge blocks in team;
# single warns either way; non-boundary commands are never gated.

setup() {
  GATE="$BATS_TEST_DIRNAME/../hooks/gate.sh"
  STUBS="$BATS_TEST_DIRNAME/stubs"
  REPO="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$REPO"
  (cd "$REPO" && git init -q && git config user.email t@e.st && git config user.name t)
  # Point policy-gate at the fake loader (first path it searches is under $HOME).
  export HOME="$BATS_TEST_TMPDIR/home"
  mkdir -p "$HOME/.config/agents/skills/policy"
  cp "$STUBS/policy_loader.py" "$HOME/.config/agents/skills/policy/policy_loader.py"
  PATH="$STUBS:$PATH"
}

# run_gate <command-text>; FAKE_* env set per test simulate policy + forge state.
run_gate() { run sh -c "printf '%s' '{\"command\":\"$1\"}' | sh '$GATE'"; }

@test "team · merge a green + reviewed PR ⇒ pass (no SWE_GATE_OK)" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=0 FAKE_REVIEW=APPROVED
  run_gate "gh pr merge 7 --squash"
  [ "$status" -eq 0 ]
}

@test "team · merge a red PR ⇒ block" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=APPROVED
  run_gate "gh pr merge 7 --squash"
  [ "$status" -eq 2 ]
}

@test "team · merge an unreviewed PR ⇒ block" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=0 FAKE_REVIEW=REVIEW_REQUIRED
  run_gate "gh pr merge 7 --squash"
  [ "$status" -eq 2 ]
}

@test "team · merge with no resolvable PR ⇒ block (never merge unverified)" {
  export FAKE_MODE=team FAKE_PR_NUMBER=
  run_gate "gh pr merge --squash"
  [ "$status" -eq 2 ]
}

@test "single · merge a red PR ⇒ warn (allow)" {
  export FAKE_MODE=single FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=APPROVED
  run_gate "gh pr merge 7 --squash"
  [ "$status" -eq 0 ]
}

@test "non-boundary command ⇒ never gated" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1
  run_gate "ls -la"
  [ "$status" -eq 0 ]
}

@test "team · git push to a red feature branch ⇒ not gated (push is not a merge)" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=REVIEW_REQUIRED
  run_gate "git push origin HEAD"
  [ "$status" -eq 0 ]
}

@test "SWE_GATE_OK=1 overrides a red PR in team" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 SWE_GATE_OK=1
  run_gate "gh pr merge 7 --squash"
  [ "$status" -eq 0 ]
}

@test "team · commit with no red-first artifact yet ⇒ allow (not the merge gate)" {
  export FAKE_MODE=team
  run_gate "git commit -m wip"
  [ "$status" -eq 0 ]
}

@test "team · local git merge with no PR ⇒ block (the local binding documents SWE_GATE_OK)" {
  export FAKE_MODE=team FAKE_PR_NUMBER=
  run_gate "git merge --ff-only kauki/feat/a/b"
  [ "$status" -eq 2 ]
}

@test "team · local git merge with SWE_GATE_OK=1 ⇒ pass" {
  export FAKE_MODE=team FAKE_PR_NUMBER='' SWE_GATE_OK=1
  run_gate "git merge --ff-only kauki/feat/a/b"
  [ "$status" -eq 0 ]
}

@test "single · local git merge with no PR ⇒ warn (allow)" {
  export FAKE_MODE=single FAKE_PR_NUMBER=
  run_gate "git merge --ff-only kauki/feat/a/b"
  [ "$status" -eq 0 ]
}

# run_gate_json <command-text>: the real Claude Code payload shape, JSON-encoded safely.
run_gate_json() {
  local payload
  payload=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1")
  run sh -c "printf '%s' \"\$1\" | sh '$GATE'" sh "$payload"
}

@test "team · a block exits 2 (exit 1 would not block in Claude Code) and says why on stderr" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=APPROVED
  run_gate_json "gh pr merge 7 --squash"
  [ "$status" -eq 2 ]
}

@test "team · boundary words inside a commit message or heredoc are not a boundary" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=REVIEW_REQUIRED
  run_gate_json "gh issue create --title x --body 'run gh pr merge 7 later'"
  [ "$status" -eq 0 ]
  run_gate_json "cat > notes.md <<'EOF'
gh pr merge 7
EOF"
  [ "$status" -eq 0 ]
  run_gate_json "echo git merge main"
  [ "$status" -eq 0 ]
  run_gate_json "grep -r 'pr create' docs"
  [ "$status" -eq 0 ]
}

@test "team · a merge after an env prefix, a wrapper or a separator is still a boundary" {
  export FAKE_MODE=team FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=APPROVED
  for c in "GH_TOKEN=x gh pr merge 7" "cd /r && gh pr merge 7 --squash" "env gh pr merge 7" "git -C /r merge --ff-only x"; do
    run_gate_json "$c"
    [ "$status" -eq 2 ]
  done
}

@test "team · a commit message that mentions git merge is a commit, not a merge" {
  export FAKE_MODE=team FAKE_PR_NUMBER='' FAKE_CHECKS_EXIT=1
  run_gate_json "git commit -m 'git merge notes'"
  [ "$status" -eq 0 ]
}
