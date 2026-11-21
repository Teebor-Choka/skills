#!/usr/bin/env bats
# The SessionStart hook injects the resolved .agents/policy as session context. It must find the
# `policy` skill's loader wherever the harness installs it (the plugin-delivered skill is not in
# ~/.config/agents/skills) and must stay silent, never fail, when the loader or policy is unusable.

setup() {
  # A copy outside the repo: run in place, find-loader.sh would find this repo's ai/harness loader.
  mkdir -p "$BATS_TEST_TMPDIR/plugin"
  cp -R "$BATS_TEST_DIRNAME/../hooks" "$BATS_TEST_DIRNAME/../skills" "$BATS_TEST_TMPDIR/plugin/"
  HOOK="$BATS_TEST_TMPDIR/plugin/hooks/policy-context.sh"
  STUBS="$BATS_TEST_DIRNAME/stubs"
  export HOME="$BATS_TEST_TMPDIR/home"
  export CLAUDE_PROJECT_DIR="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$HOME" "$CLAUDE_PROJECT_DIR"
  export FAKE_JSON='{"mode": "team", "practices": {"scope": "ATDD", "task": "TDD"}}'
}

install_loader() { # install_loader <dir under $HOME>
  mkdir -p "$HOME/$1"
  cp "$STUBS/policy_loader.py" "$HOME/$1/policy_loader.py"
}

@test "loader under ~/.agents/skills/policy ⇒ SessionStart context carries the policy" {
  install_loader .agents/skills/policy
  run sh "$HOOK"
  [ "$status" -eq 0 ]
  printf '%s' "$output" | python3 -c '
import json, sys
o = json.load(sys.stdin)["hookSpecificOutput"]
assert o["hookEventName"] == "SessionStart"
assert "\"mode\": \"team\"" in o["additionalContext"]
'
}

@test "loader under ~/.config/agents/skills/policy ⇒ also found" {
  install_loader .config/agents/skills/policy
  run sh "$HOOK"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"additionalContext"'* ]]
}

@test "no loader installed ⇒ silent, exit 0" {
  run sh "$HOOK"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "loader fails (malformed policy) ⇒ silent, exit 0" {
  install_loader .agents/skills/policy
  FAKE_FAIL=1 run sh "$HOOK"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "loader prints nothing ⇒ silent, exit 0" {
  install_loader .agents/skills/policy
  FAKE_JSON='' run sh "$HOOK"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
