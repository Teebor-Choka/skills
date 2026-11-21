#!/usr/bin/env bats
# Tests for babysit and its forges/ backends. Stub forge CLIs (`gh`, `glab`) on PATH serve canned
# GraphQL responses in sequence.

bats_require_minimum_version 1.5.0

setup() {
  BABYSIT="$BATS_TEST_DIRNAME/babysit"
  TMP="$(cd "$(mktemp -d)" && pwd -P)"
  export GIT_CONFIG_GLOBAL="$TMP/gitconfig"
  export GIT_CONFIG_SYSTEM=/dev/null
  # Hook-safe: a pre-commit hook exports GIT_DIR/GIT_INDEX_FILE, which would point git at the
  # outer repo instead of the temp one.
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
  git init -q -b feat "$TMP/repo"
  git -C "$TMP/repo" remote add origin git@github.com:o/r.git

  # Stub gh: the Nth call prints the highest-numbered $GH_STUB_DIR/K.json with K <= N, so a gap
  # repeats the previous response. A response file holding the word FAIL makes that call fail.
  export GH_STUB_DIR="$TMP/stub"
  mkdir -p "$GH_STUB_DIR" "$TMP/bin"
  cat >"$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
# Marking ready/merge is recorded, not answered from the sequence; GH_STUB_READY_FAIL and
# GH_STUB_MERGE_FAIL make the respective call fail.
case "$*" in
  "pr ready"* | "mr update"*)
    echo "$*" >>"$GH_STUB_DIR/ready"
    [ -z "${GH_STUB_READY_FAIL:-}" ] || { echo "cannot mark ready" >&2; exit 1; }
    exit 0
    ;;
  "pr merge"* | "mr merge"*)
    echo "$*" >>"$GH_STUB_DIR/merge"
    [ -z "${GH_STUB_MERGE_FAIL:-}" ] || { echo "cannot enqueue" >&2; exit 1; }
    exit 0
    ;;
esac
n=$(( $(cat "$GH_STUB_DIR/count" 2>/dev/null || echo 0) + 1 ))
echo "$n" >"$GH_STUB_DIR/count"
k=$n
while [ ! -f "$GH_STUB_DIR/$k.json" ]; do k=$((k - 1)); done
f="$GH_STUB_DIR/$k.json"
grep -qx FAIL "$f" && { echo "gh: HTTP 502" >&2; exit 1; }
cat "$f"
EOF
  chmod +x "$TMP/bin/gh"
  cp "$TMP/bin/gh" "$TMP/bin/glab"
  export PATH="$TMP/bin:$PATH"
}

teardown() {
  rm -rf "$TMP"
}

# resp N [key=json ...]: write response N, a PR with defaults overridden by jq assignments.
resp() {
  local n=$1
  shift
  local filter='.'
  for kv in "$@"; do filter="$filter | .${kv%%=*} = ${kv#*=}"; done
  jq -n "{
    state: \"OPEN\", isDraft: false, mergeStateStatus: \"BLOCKED\", reviewDecision: null,
    number: 7, url: \"https://github.com/o/r/pull/7\",
    commits: {nodes: [{commit: {statusCheckRollup: {state: \"PENDING\", contexts: {nodes: []}}}}]},
    reviewThreads: {nodes: []}, comments: {nodes: []}, reviews: {nodes: []}
  } | $filter | {data: {viewer: {login: \"me\"}, repository: {pullRequests: {nodes: [.]}}}}" \
    >"$GH_STUB_DIR/$n.json"
}

comment() { echo "{databaseId: $1, author: {login: \"$2\"}, body: \"$3\", url: \"u$1\"}"; }
thread() { echo "{id: \"$1\", isResolved: $2, path: \"src/a.rs\", line: 3, comments: {nodes: [$(comment "$3" rev "$4")]}}"; }

events() { jq -r .event <<<"$output" | paste -sd' ' -; }

@test "first poll emits one snapshot with outstanding threads and failing checks" {
  resp 1 'reviewThreads.nodes=['"$(thread T1 false 11 'fix this')"','"$(thread T2 true 12 'done')"']' \
    'commits.nodes[0].commit.statusCheckRollup={state: "FAILURE", contexts: {nodes: [{__typename: "CheckRun", name: "lint", conclusion: "FAILURE", status: "COMPLETED"}, {__typename: "CheckRun", name: "test", conclusion: "SUCCESS", status: "COMPLETED"}]}}'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(events)" = snapshot ]
  [ "$(jq -c .failing <<<"$output")" = '["lint"]' ]
  [ "$(jq -r '.threads | length' <<<"$output")" = 1 ]
  [ "$(jq -r '.threads[0].body' <<<"$output")" = "fix this" ]
}

@test "re-running from saved state emits nothing new" {
  resp 1 'comments.nodes=['"$(comment 1 alice hi)"']'
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "emits only the deltas: new comment, new thread, checks transition, behind" {
  resp 1
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  resp 2 'comments.nodes=['"$(comment 5 alice 'please rename')"']' \
    'reviewThreads.nodes=['"$(thread T9 false 21 'nit: typo')"']' \
    'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' \
    'mergeStateStatus="BEHIND"'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(events)" = "comment thread checks merge" ]
  [ "$(jq -r 'select(.event=="comment").body' <<<"$output")" = "please rename" ]
  [ "$(jq -r 'select(.event=="thread").id' <<<"$output")" = T9 ]
  [ "$(jq -r 'select(.event=="checks").state' <<<"$output")" = SUCCESS ]
  [ "$(jq -r 'select(.event=="merge").status' <<<"$output")" = BEHIND ]
}

@test "events carry no empty fields and no urls, only ids" {
  resp 1
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$output" = '{"event":"snapshot","state":"OPEN","merge":"BLOCKED","checks":"PENDING"}' ]
  resp 2 'comments.nodes=['"$(comment 5 alice hi)"']'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$output" = '{"event":"comment","id":5,"author":"alice","body":"hi"}' ]
}

@test "the viewer's own comments still surface, tagged self" {
  resp 1
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  resp 2 'comments.nodes=['"$(comment 8 me 'also bump the version')"']'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = comment ]
  [ "$(jq -r .self <<<"$output")" = true ]
}

@test "a reply on an existing unresolved thread re-emits it; resolving it is silent" {
  resp 1 'reviewThreads.nodes=['"$(thread T1 false 11 'fix this')"']'
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  resp 2 'reviewThreads.nodes=['"$(thread T1 false 12 'still wrong')"']'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = thread ]
  resp 3 'reviewThreads.nodes=['"$(thread T1 true 12 'still wrong')"']'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ -z "$output" ]
}

@test "pending checks and transient merge states stay quiet" {
  resp 1 'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' 'mergeStateStatus="CLEAN"'
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  resp 2 'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' 'mergeStateStatus="UNKNOWN"'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ -z "$output" ]
  # UNKNOWN is not remembered, so settling back to CLEAN is not a change either.
  resp 3 'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' 'mergeStateStatus="CLEAN"'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ -z "$output" ]
  # Checks going back to pending (a new push) is not news; the settled result will be.
  resp 4 'mergeStateStatus="CLEAN"'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ -z "$output" ]
}

@test "review with a verdict surfaces; an empty COMMENTED review does not" {
  resp 1
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  resp 2 'reviews.nodes=[{databaseId: 30, author: {login: "bob"}, state: "COMMENTED", body: "", url: "r30"}, {databaseId: 31, author: {login: "bob"}, state: "CHANGES_REQUESTED", body: "see threads", url: "r31"}]' \
    'reviewDecision="CHANGES_REQUESTED"'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = review ]
  [ "$(jq -r .state <<<"$output")" = CHANGES_REQUESTED ]
}

@test "long bodies are truncated so each event stays one short line" {
  resp 1
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  long=$(printf 'x%.0s' $(seq 1 1000))
  resp 2 'comments.nodes=['"$(comment 5 alice "$long")"']'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(wc -l <<<"$output")" -eq 1 ]
  [ "$(jq -r '.body | length' <<<"$output")" -le 201 ]
}

@test "merged: emits merged and exits 0" {
  resp 1 'state="MERGED"'
  run "$BABYSIT" -i 1 --no-land -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(jq -c 'select(.event=="merged")' <<<"$output")" = '{"event":"merged"}' ]
}

@test "closed unmerged: emits closed and exits 5" {
  resp 1
  resp 2 'state="CLOSED"'
  run "$BABYSIT" -i 1 -C "$TMP/repo"
  [ "$status" -eq 5 ]
  [ "$(events)" = "snapshot closed" ]
}

@test "heartbeat lines arrive on the set cadence while nothing changes" {
  resp 1
  resp 5 'state="MERGED"'
  run "$BABYSIT" -i 1 --no-land --heartbeat 1 -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(jq -r 'select(.event=="heartbeat")' <<<"$output" | grep -c heartbeat)" -ge 2 ]
  [ "$(jq -r 'select(.event=="heartbeat").unresolved' <<<"$output" | head -1)" = 0 ]
}

@test "no heartbeat unless asked" {
  resp 1
  resp 4 'state="MERGED"'
  run "$BABYSIT" -i 1 --no-land -C "$TMP/repo"
  [ "$(events)" = "snapshot merged" ]
}

@test "a transient gh failure is retried silently" {
  resp 1
  echo FAIL >"$GH_STUB_DIR/2.json"
  resp 3 'state="MERGED"'
  run "$BABYSIT" -i 1 --no-land -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(events)" = "snapshot merged" ]
}

@test "persistent gh failure emits an error event and exits 1, never goes silent" {
  echo FAIL >"$GH_STUB_DIR/1.json"
  run "$BABYSIT" -i 1 --max-errors 2 -C "$TMP/repo"
  [ "$status" -eq 1 ]
  [ "$(events)" = error ]
}

@test "no PR for the branch is an error after retries" {
  echo '{"data": {"viewer": {"login": "me"}, "repository": {"pullRequests": {"nodes": []}}}}' >"$GH_STUB_DIR/1.json"
  run "$BABYSIT" -i 1 --max-errors 2 -C "$TMP/repo"
  [ "$status" -eq 1 ]
  [ "$(jq -r .error <<<"$output")" = "no change request found for 'feat'" ]
}

@test "--quiet prints only the terminal event" {
  resp 1 'comments.nodes=['"$(comment 1 alice hi)"']'
  resp 2 'comments.nodes=['"$(comment 1 alice hi)"','"$(comment 2 bob yo)"']' 'state="MERGED"'
  run "$BABYSIT" -i 1 --no-land --quiet -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$output" = '{"event":"merged"}' ]
}

@test "merged is handed to pr-landed by default and its result forwarded" {
  git -C "$TMP/repo" remote remove origin
  resp 1 'state="MERGED"'
  run "$BABYSIT" -i 1 --quiet --forge github -C "$TMP/repo"
  # The temp repo has no origin, so pr-landed's own refusal proves the hand-off happened.
  [ "$status" -eq 1 ]
  [ "$(sed -n 1p <<<"$output")" = '{"event":"merged"}' ]
  [ "$(sed -n 2p <<<"$output" | jq -r .error)" = "cannot determine the default branch (no origin/HEAD, origin/main or origin/master)" ]
}

@test "usage errors exit 2" {
  run "$BABYSIT" --bogus
  [ "$status" -eq 2 ]
  run "$BABYSIT" -C "$TMP/nope"
  [ "$status" -eq 2 ]
}

# glresp N [key=json ...]: a GitLab MR response, defaults overridden by jq assignments.
glresp() {
  local n=$1
  shift
  local filter='.'
  for kv in "$@"; do filter="$filter | .${kv%%=*} = ${kv#*=}"; done
  jq -n "{
    state: \"opened\", draft: false, detailedMergeStatus: \"NOT_APPROVED\", approved: false,
    approvedBy: {nodes: []}, headPipeline: {status: \"RUNNING\", jobs: {nodes: []}},
    discussions: {nodes: []}
  } | $filter | {data: {currentUser: {username: \"me\"}, project: {mergeRequests: {nodes: [.]}}}}" \
    >"$GH_STUB_DIR/$n.json"
}

note() { echo "{id: \"gid://gitlab/Note/$1\", system: false, body: \"$3\", author: {username: \"$2\"}, position: {newPath: \"lib/x.rb\", newLine: 9}}"; }

@test "gitlab: detected from origin, MR mapped onto the shared events" {
  git -C "$TMP/repo" remote set-url origin https://gitlab.example.com/grp/sub/proj.git
  glresp 1 'discussions.nodes=[{id: "D1", resolvable: true, resolved: false, notes: {nodes: [{id: "gid://gitlab/Note/0", system: true, body: "changed line", author: {username: "x"}, position: null}, '"$(note 1 rev 'rename this')"']}}]'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$output" = '{"event":"snapshot","state":"OPEN","merge":"BLOCKED","checks":"PENDING","threads":[{"id":"D1","path":"lib/x.rb","line":9,"author":"rev","body":"rename this"}]}' ]
  glresp 2 'discussions.nodes=[{id: "D2", resolvable: false, resolved: false, notes: {nodes: ['"$(note 2 me 'pls rebase')"']}}]' \
    'headPipeline={status: "FAILED", jobs: {nodes: [{name: "rspec", status: "FAILED"}, {name: "lint", status: "SUCCESS"}]}}' \
    'detailedMergeStatus="NEED_REBASE"' 'approved=true' 'approvedBy.nodes=[{username: "rev"}]'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = "comment review checks merge" ]
  [ "$(jq -c 'select(.event=="comment")' <<<"$output")" = '{"event":"comment","id":"gid://gitlab/Note/2","author":"me","self":true,"body":"pls rebase"}' ]
  [ "$(jq -r 'select(.event=="review").state' <<<"$output")" = APPROVED ]
  [ "$(jq -c 'select(.event=="checks")' <<<"$output")" = '{"event":"checks","state":"FAILURE","failing":["rspec"]}' ]
  [ "$(jq -r 'select(.event=="merge").status' <<<"$output")" = BEHIND ]
}

@test "gitlab: merged MR ends the watch" {
  git -C "$TMP/repo" remote set-url origin git@gitlab.com:grp/proj.git
  glresp 1 'state="merged"'
  run "$BABYSIT" -i 1 --no-land --quiet -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$output" = '{"event":"merged"}' ]
}

@test "--forge and babysit.forge override the origin host" {
  git -C "$TMP/repo" remote set-url origin git@code.corp.example:grp/proj.git
  glresp 1 'state="merged"'
  run "$BABYSIT" --once --quiet --no-land --forge gitlab -C "$TMP/repo"
  [ "$output" = '{"event":"merged"}' ]
  git -C "$TMP/repo" config babysit.forge gitlab
  run "$BABYSIT" --once --quiet --no-land -C "$TMP/repo"
  [ "$output" = '{"event":"merged"}' ]
}

@test "an undetectable or unknown forge is a usage error naming the backends" {
  git -C "$TMP/repo" remote set-url origin git@code.corp.example:grp/proj.git
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$status" -eq 2 ]
  [[ "$output" == *"pass --forge (github gitlab)"* ]]
  run "$BABYSIT" --once --forge ../babysit -C "$TMP/repo"
  [ "$status" -eq 2 ]
  [[ "$output" == *"unknown forge"* ]]
}

@test "a missing forge CLI is an immediate error, and only the chosen forge's CLI is needed" {
  rm "$TMP/bin/gh"
  git -C "$TMP/repo" remote set-url origin git@gitlab.com:grp/proj.git
  glresp 1 'state="merged"'
  run "$BABYSIT" --once --quiet --no-land -C "$TMP/repo"
  [ "$output" = '{"event":"merged"}' ]
  git -C "$TMP/repo" remote set-url origin git@github.com:o/r.git
  # Only jq and git beside the stubs, so no real gh on PATH can answer.
  mkdir "$TMP/tools"
  ln -s "$(command -v jq)" "$(command -v git)" "$TMP/tools/"
  export PATH="$TMP/bin:$TMP/tools:/usr/bin:/bin"
  run "$BABYSIT" -i 1 --max-errors 9 -C "$TMP/repo"
  [ "$status" -eq 1 ]
  [ "$(jq -r .error <<<"$output")" = "gh is required for GitHub" ]
}

@test "starting on a draft marks it ready at once, whatever CI says" {
  resp 1 'isDraft=true' 'commits.nodes[0].commit.statusCheckRollup={state: "FAILURE", contexts: {nodes: []}}'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(events)" = "snapshot ready" ]
  [ "$(cat "$GH_STUB_DIR/ready")" = "pr ready feat" ]
  # Once per run: a second run tries again, but later polls of that run do not.
  resp 2 'isDraft=true'
  resp 4 'isDraft=true' 'state="MERGED"'
  run "$BABYSIT" -i 1 --no-land -C "$TMP/repo"
  [ "$(wc -l <"$GH_STUB_DIR/ready")" -eq 2 ]
}

@test "a change request that is not a draft is left alone" {
  resp 1
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = snapshot ]
  [ ! -e "$GH_STUB_DIR/ready" ]
}

@test "a failed ready is reported and the watch goes on" {
  resp 1 'isDraft=true'
  resp 2 'isDraft=true' 'state="MERGED"'
  GH_STUB_READY_FAIL=1 run "$BABYSIT" -i 1 --no-land -C "$TMP/repo"
  [ "$status" -eq 0 ]
  [ "$(events)" = "snapshot ready_failed merged" ]
  [ "$(jq -r 'select(.event=="ready_failed").error' <<<"$output")" = "cannot mark ready" ]
}

@test "gitlab: a draft MR is marked ready with glab" {
  git -C "$TMP/repo" remote set-url origin git@gitlab.com:grp/proj.git
  glresp 1 'draft=true'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = "snapshot ready" ]
  [ "$(cat "$GH_STUB_DIR/ready")" = "mr update feat --ready" ]
}

clean_approved() { resp "$1" 'reviewDecision="APPROVED"' 'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' 'mergeStateStatus="CLEAN"'; }

@test "automerge is off by default: a clean, approved PR is never enqueued" {
  clean_approved 1
  run "$BABYSIT" --once -C "$TMP/repo"
  [ ! -e "$GH_STUB_DIR/merge" ]
}

@test "automerge enqueues once babysit.automerge is set and the PR is clean and approved" {
  git -C "$TMP/repo" config babysit.automerge true
  clean_approved 1
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = "snapshot enqueued" ]
  [ "$(cat "$GH_STUB_DIR/merge")" = "pr merge feat --auto" ]
}

@test "automerge does not fire while a thread is unresolved, even if approved and green" {
  git -C "$TMP/repo" config babysit.automerge true
  resp 1 'reviewDecision="APPROVED"' 'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' 'mergeStateStatus="CLEAN"' \
    'reviewThreads.nodes=['"$(thread T1 false 11 'fix this')"']'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ ! -e "$GH_STUB_DIR/merge" ]
}

@test "a failed enqueue is reported and the watch goes on" {
  git -C "$TMP/repo" config babysit.automerge true
  clean_approved 1
  resp 2 'reviewDecision="APPROVED"' 'commits.nodes[0].commit.statusCheckRollup={state: "SUCCESS", contexts: {nodes: []}}' 'mergeStateStatus="CLEAN"' 'state="MERGED"'
  GH_STUB_MERGE_FAIL=1 run "$BABYSIT" -i 1 --no-land -C "$TMP/repo"
  [ "$(events)" = "snapshot enqueue_failed merged" ]
  [ "$(jq -r 'select(.event=="enqueue_failed").error' <<<"$output")" = "cannot enqueue" ]
}

@test "gitlab: automerge calls glab mr merge --auto-merge" {
  git -C "$TMP/repo" remote set-url origin git@gitlab.com:grp/proj.git
  git -C "$TMP/repo" config babysit.automerge true
  glresp 1 'approved=true' 'approvedBy.nodes=[{username: "rev"}]' 'detailedMergeStatus="MERGEABLE"' 'headPipeline={status: "SUCCESS", jobs: {nodes: []}}'
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$(events)" = "snapshot enqueued" ]
  [ "$(cat "$GH_STUB_DIR/merge")" = "mr merge feat --auto-merge" ]
}

@test "a new commit failing the same checks reports again, even if pending was never seen" {
  red='commits.nodes[0].commit.statusCheckRollup={state: "FAILURE", contexts: {nodes: [{__typename: "CheckRun", name: "lint", conclusion: "FAILURE", status: "COMPLETED"}]}}'
  resp 1 'commits.nodes[0].commit.oid="aaa"' "$red"
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  resp 2 'commits.nodes[0].commit.oid="bbb"' "$red"
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$output" = '{"event":"checks","state":"FAILURE","failing":["lint"]}' ]
  # The same commit polled again stays quiet.
  run "$BABYSIT" --once -C "$TMP/repo"
  [ -z "$output" ]
}

@test "gitlab: a new commit failing the same pipeline job reports again" {
  git -C "$TMP/repo" remote set-url origin git@gitlab.com:grp/proj.git
  red='headPipeline={status: "FAILED", jobs: {nodes: [{name: "rspec", status: "FAILED"}]}}'
  glresp 1 'diffHeadSha="aaa"' "$red"
  "$BABYSIT" --once -C "$TMP/repo" >/dev/null
  glresp 2 'diffHeadSha="bbb"' "$red"
  run "$BABYSIT" --once -C "$TMP/repo"
  [ "$output" = '{"event":"checks","state":"FAILURE","failing":["rspec"]}' ]
}
