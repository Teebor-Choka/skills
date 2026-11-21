#!/usr/bin/env bats
# Tests for pr-state. A stub `gh` serves canned GraphQL and `run list` output.

setup() {
  PR_STATE="$BATS_TEST_DIRNAME/pr-state"
  TMP="$(cd "$(mktemp -d)" && pwd -P)"
  export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_SYSTEM=/dev/null
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
  git init -q -b feat "$TMP/repo"
  git -C "$TMP/repo" -c user.name=t -c user.email=t@e.x -c commit.gpgsign=false commit -q --allow-empty -m init
  mkdir -p "$TMP/bin"
  # The resolved bash, not /usr/bin/env: the Linux nix sandbox has no /usr/bin/env.
  printf '#!%s\n' "$(command -v bash)" >"$TMP/bin/gh"
  cat >>"$TMP/bin/gh" <<'STUB'
case "$*" in
  "api graphql"*) [ -z "${GH_FAIL:-}" ] || { echo boom >&2; exit 1; }; cat "$GH_PR" ;;
  "run list"*) echo "${GH_RUN:-[]}" ;;
esac
STUB
  chmod +x "$TMP/bin/gh"
  export PATH="$TMP/bin:$PATH" GH_PR="$TMP/pr.json"
}

teardown() { rm -rf "$TMP"; }

# pr [jq assignments]: write a PR response, defaults overridden by the arguments.
pr() {
  local filter='.'
  for kv in "$@"; do filter="$filter | .${kv%%=*} = ${kv#*=}"; done
  jq -n "{state: \"OPEN\", isDraft: false, mergeStateStatus: \"CLEAN\", reviewDecision: \"APPROVED\",
    mergeQueueEntry: null,
    commits: {nodes: [{commit: {oid: \"abcdef1234\", statusCheckRollup: {state: \"SUCCESS\"}}}]},
    reviewThreads: {nodes: []}} | $filter
    | {data: {repository: {pullRequests: {nodes: [.]}}}}" >"$GH_PR"
}

next() { grep '^next:' <<<"$output"; }

@test "clean approved PR is ready to merge" {
  pr
  run "$PR_STATE" -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [[ "$(next)" == *"ready: merge only with approval"* ]]
}

@test "an unresolved thread comes before everything else" {
  pr 'reviewThreads.nodes=[{isResolved: false}]' 'reviewDecision="CHANGES_REQUESTED"'
  run "$PR_STATE" -C "$TMP/repo"
  [[ "$(next)" == *"resolve 1 open thread"* ]]
}

@test "a queued PR waits" {
  pr 'mergeQueueEntry={state: "QUEUED", position: 2}'
  run "$PR_STATE" -C "$TMP/repo"
  [[ "$output" == *"queue=QUEUED/2"* ]]
  [[ "$(next)" == *"queued: wait"* ]]
}

@test "a run on an older commit is stale" {
  pr
  GH_RUN='[{"headSha":"0000000aaaa","status":"completed","conclusion":"failure"}]' \
    run "$PR_STATE" -C "$TMP/repo"
  [[ "$output" == *"run=0000000 completed failure stale"* ]]
  [[ "$(next)" == *"older commit"* ]]
}

@test "failing checks forbid a blind rerun" {
  pr 'commits.nodes[0].commit.statusCheckRollup={state: "FAILURE"}'
  run "$PR_STATE" -C "$TMP/repo"
  [[ "$(next)" == *"do not rerun blind"* ]]
}

@test "no PR exits 2" {
  jq -n '{data: {repository: {pullRequests: {nodes: []}}}}' >"$GH_PR"
  run "$PR_STATE" -C "$TMP/repo"
  [ "$status" -eq 2 ]
}

@test "a gh failure exits 1 with a message" {
  GH_FAIL=1 run "$PR_STATE" -C "$TMP/repo"
  [ "$status" -eq 1 ]
  [[ "$output" == *"gh api graphql failed"* ]]
}
