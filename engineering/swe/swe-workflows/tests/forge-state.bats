#!/usr/bin/env bats
# The GitHub binding's state query. gate.sh trusts its exit code to decide --ok, so the
# green/red/approved/unreviewed boundaries are the contract under test.
#   exit 0 = condition MET · 1 = genuinely UNMET · 2 = INDETERMINATE (no gh / no PR)

setup() {
  SWE="$BATS_TEST_DIRNAME/../skills/implement/scripts"
  FORGE="$SWE/forge-state.sh"
  STUBS="$BATS_TEST_DIRNAME/stubs"
  REPO="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$REPO"
  (cd "$REPO" && git init -q && git config user.email t@e.st && git config user.name t)
  # Put the gh stub first on PATH.
  PATH="$STUBS:$PATH"
}

run_forge() { run sh "$FORGE" "$REPO" "$@"; }

@test "integrate: green CI + APPROVED review ⇒ met (0)" {
  FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=0 FAKE_REVIEW=APPROVED run_forge integrate
  [ "$status" -eq 0 ]
}

@test "integrate: failing CI ⇒ unmet (1)" {
  FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=1 FAKE_REVIEW=APPROVED run_forge integrate
  [ "$status" -eq 1 ]
}

@test "integrate: pending CI ⇒ unmet (1)" {
  FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=8 FAKE_REVIEW=APPROVED run_forge integrate
  [ "$status" -eq 1 ]
}

@test "integrate: green CI but no approval ⇒ unmet (1)" {
  FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=0 FAKE_REVIEW=REVIEW_REQUIRED run_forge integrate
  [ "$status" -eq 1 ]
}

@test "integrate: green CI but changes requested ⇒ unmet (1)" {
  FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=0 FAKE_REVIEW=CHANGES_REQUESTED run_forge integrate
  [ "$status" -eq 1 ]
}

@test "integrate: no PR for the branch ⇒ indeterminate (2)" {
  FAKE_PR_NUMBER='' FAKE_CHECKS_EXIT=0 FAKE_REVIEW=APPROVED run_forge integrate
  [ "$status" -eq 2 ]
}

# Ready = implementation complete, feedback requested. CI and review are the feedback, so they
# never gate it: the forge has no say, whatever state it is in.
@test "ready: not a forge fact ⇒ indeterminate (2) whatever CI or review say" {
  for checks in 0 1 8; do
    for review in APPROVED REVIEW_REQUIRED CHANGES_REQUESTED; do
      FAKE_PR_NUMBER=7 FAKE_CHECKS_EXIT=$checks FAKE_REVIEW=$review run_forge ready
      [ "$status" -eq 2 ]
    done
  done
  FAKE_PR_NUMBER='' run_forge ready
  [ "$status" -eq 2 ]
}

@test "gh not on PATH ⇒ indeterminate (2)" {
  PATH="/usr/bin:/bin" run sh "$FORGE" "$REPO" integrate
  [ "$status" -eq 2 ]
}

@test "commit: a test-touching commit in history ⇒ met (0)" {
  (cd "$REPO" && mkdir -p tests && echo x >tests/foo_test.py &&
    git add tests/foo_test.py && git commit -qm "test: red")
  run_forge commit
  [ "$status" -eq 0 ]
}

@test "commit: no test commit yet ⇒ indeterminate (2), never a hard block" {
  (cd "$REPO" && echo x >main.py && git add main.py && git commit -qm "feat: impl")
  run_forge commit
  [ "$status" -eq 2 ]
}
