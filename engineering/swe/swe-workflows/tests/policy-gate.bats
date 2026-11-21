#!/usr/bin/env bats
# policy-gate.sh error paths.

setup() {
  # A copy outside the repo: run in place, find-loader.sh would find this repo's ai/harness loader.
  mkdir -p "$BATS_TEST_TMPDIR/plugin"
  cp -R "$BATS_TEST_DIRNAME/../hooks" "$BATS_TEST_DIRNAME/../skills" "$BATS_TEST_TMPDIR/plugin/"
  GATE="$BATS_TEST_TMPDIR/plugin/skills/implement/scripts/policy-gate.sh"
  export HOME="$BATS_TEST_TMPDIR/home"
  mkdir -p "$HOME"
  unset AGENTS_POLICY_LOADER
}

@test "no loader findable => exit 2, message names harness:policy literally, no command-not-found" {
  run sh "$GATE" "$BATS_TEST_TMPDIR" show
  [ "$status" -eq 2 ]
  [[ "$output" == *"harness:policy"* ]]
  [[ "$output" != *"command not found"* ]]
}
