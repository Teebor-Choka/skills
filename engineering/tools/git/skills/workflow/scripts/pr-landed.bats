#!/usr/bin/env bats
# Tests for scripts/pr-landed. Builds a bare origin + a clone in a temp dir.

bats_require_minimum_version 1.5.0

setup() {
  # Git hooks export these; left set, every `git -C <tmp>` below targets the hook's repo.
  unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_COMMON_DIR
  PR_LANDED="$BATS_TEST_DIRNAME/pr-landed"
  TMP="$(cd "$(mktemp -d)" && pwd -P)"
  export GIT_CONFIG_GLOBAL="$TMP/gitconfig"
  export GIT_CONFIG_SYSTEM=/dev/null
  git config --global user.name test
  git config --global user.email test@example.com
  git config --global commit.gpgsign false
  git config --global init.defaultBranch main
  git config --global protocol.file.allow always

  git init -q --bare "$TMP/origin.git"
  git clone -q "$TMP/origin.git" "$TMP/repo" 2>/dev/null
  git -C "$TMP/repo" commit -q --allow-empty -m init
  git -C "$TMP/repo" push -q origin main
  git -C "$TMP/origin.git" symbolic-ref HEAD refs/heads/main
  git -C "$TMP/repo" remote set-head origin -a >/dev/null

  # A feature branch in its own worktree, pushed.
  git -C "$TMP/repo" worktree add -q -b feat "$TMP/wt-feat" origin/main
  echo x >"$TMP/wt-feat/file"
  git -C "$TMP/wt-feat" add file
  git -C "$TMP/wt-feat" commit -q -m feat
  git -C "$TMP/wt-feat" push -q -u origin feat
}

teardown() {
  rm -rf "$TMP"
}

# Merge feat into origin/main from a scratch clone, the way a PR merge would.
merge_on_origin() {
  git clone -q "$TMP/origin.git" "$TMP/scratch" 2>/dev/null
  git -C "$TMP/scratch" merge -q --no-ff -m "merge feat" origin/feat
  git -C "$TMP/scratch" push -q origin main
}

# Squash-merge feat on origin and delete the remote branch (GitHub "squash and delete").
squash_on_origin() {
  git clone -q "$TMP/origin.git" "$TMP/scratch" 2>/dev/null
  git -C "$TMP/scratch" merge -q --squash origin/feat
  git -C "$TMP/scratch" commit -q -m "squash feat"
  git -C "$TMP/scratch" push -q origin main
  git -C "$TMP/origin.git" branch -q -D feat
}

@test "lands a merged branch: ff main, drop worktree, local and remote branch" {
  merge_on_origin
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  [ ! -d "$TMP/wt-feat" ]
  run ! git -C "$TMP/repo" rev-parse --verify -q refs/heads/feat
  run ! git -C "$TMP/origin.git" rev-parse --verify -q refs/heads/feat
  [ "$(git -C "$TMP/repo" rev-parse main)" = "$(git -C "$TMP/origin.git" rev-parse main)" ]
}

@test "defaults to the current branch when run inside its worktree" {
  merge_on_origin
  cd "$TMP/wt-feat"
  run "$PR_LANDED"
  [ "$status" -eq 0 ]
  [ ! -d "$TMP/wt-feat" ]
  echo "$output" | jq -e --arg wt "$TMP/wt-feat" --arg cd "$TMP/repo" '.worktree_removed == $wt and .cd == $cd'
}

@test "lands a squash-merged branch once the remote branch is gone" {
  squash_on_origin
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  run ! git -C "$TMP/repo" rev-parse --verify -q refs/heads/feat
  [ ! -d "$TMP/wt-feat" ]
}

@test "refuses a dirty worktree and deletes nothing" {
  merge_on_origin
  echo dirty >"$TMP/wt-feat/untracked"
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 3 ]
  [ -d "$TMP/wt-feat" ]
  git -C "$TMP/repo" rev-parse --verify -q refs/heads/feat
  git -C "$TMP/origin.git" rev-parse --verify -q refs/heads/feat
}

@test "refuses a branch that is not merged and deletes nothing" {
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 4 ]
  [ -d "$TMP/wt-feat" ]
  git -C "$TMP/origin.git" rev-parse --verify -q refs/heads/feat
}

@test "--force lands an unmerged branch" {
  run "$PR_LANDED" --force -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  [ ! -d "$TMP/wt-feat" ]
  run ! git -C "$TMP/repo" rev-parse --verify -q refs/heads/feat
}

@test "--force still refuses a dirty worktree" {
  echo dirty >"$TMP/wt-feat/untracked"
  run "$PR_LANDED" --force -C "$TMP/repo" feat
  [ "$status" -eq 3 ]
  [ -d "$TMP/wt-feat" ]
}

@test "refuses to land the default branch" {
  run "$PR_LANDED" -C "$TMP/repo" main
  [ "$status" -eq 2 ]
  git -C "$TMP/repo" rev-parse --verify -q refs/heads/main
}

@test "works for a branch with no worktree" {
  merge_on_origin
  git -C "$TMP/repo" worktree remove "$TMP/wt-feat"
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  run ! git -C "$TMP/repo" rev-parse --verify -q refs/heads/feat
  run ! git -C "$TMP/origin.git" rev-parse --verify -q refs/heads/feat
}

@test "skips the remote delete when the remote branch is already gone" {
  merge_on_origin
  git -C "$TMP/origin.git" branch -q -D feat
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
}

@test "does not merge or push the default branch" {
  merge_on_origin
  before=$(git -C "$TMP/origin.git" rev-parse main)
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  [ "$(git -C "$TMP/origin.git" rev-parse main)" = "$before" ]
}

@test "exits 2 for an unknown branch" {
  run "$PR_LANDED" -C "$TMP/repo" nope
  [ "$status" -eq 2 ]
}

@test "exits 2 on the default branch with no argument" {
  run "$PR_LANDED" -C "$TMP/repo"
  [ "$status" -eq 2 ]
}

@test "prints one JSON object by default" {
  merge_on_origin
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | wc -l)" -eq 1 ]
  echo "$output" | jq -e --arg wt "$TMP/wt-feat" --arg repo "$TMP/repo" --arg sha "$(git -C "$TMP/repo" rev-parse --short main)" \
    '.ok == true and .exit == 0 and .branch == "feat" and .default_branch == "main" and .default_sha == $sha
     and .worktree_removed == $wt and .local_branch_deleted == true and .remote_branch_deleted == true and .cd == $repo'
}

@test "JSON has null worktree and cd when the branch has no worktree" {
  merge_on_origin
  git -C "$TMP/repo" worktree remove "$TMP/wt-feat"
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.worktree_removed == null and .cd == null'
}

@test "JSON reports remote_branch_deleted false when the remote branch is already gone" {
  merge_on_origin
  git -C "$TMP/origin.git" branch -q -D feat
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.remote_branch_deleted == false'
}

@test "reports a dirty worktree as JSON with exit 3" {
  merge_on_origin
  echo dirty >"$TMP/wt-feat/untracked"
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 3 ]
  echo "$output" | jq -e '.ok == false and .exit == 3 and (.error | test("dirty"))'
}

@test "reports an unlanded branch as JSON with exit 4" {
  run "$PR_LANDED" -C "$TMP/repo" feat
  [ "$status" -eq 4 ]
  echo "$output" | jq -e '.ok == false and .exit == 4 and (.error | test("not merged"))'
}

@test "reports usage errors as JSON with exit 2" {
  run "$PR_LANDED" --bogus
  [ "$status" -eq 2 ]
  echo "$output" | jq -e '.ok == false and .exit == 2 and (.error | test("unknown option"))'
}

@test "-o plain prints progress lines on stdout and no JSON" {
  merge_on_origin
  run --separate-stderr "$PR_LANDED" -o plain -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  [[ "$output" == *"fast-forwarded main to "* ]]
  [[ "$output" == *"removed worktree $TMP/wt-feat"* ]]
  [[ "$output" == *"deleted local branch feat"* ]]
  [[ "$output" == *"deleted origin/feat"* ]]
  [[ "$output" != *'"ok"'* ]]
}

@test "--output plain sends errors to stderr and leaves stdout empty" {
  run --separate-stderr "$PR_LANDED" -o plain -C "$TMP/repo" feat
  [ "$status" -eq 4 ]
  [ -z "$output" ]
  [[ "$stderr" == "pr-landed: "*"not merged"* ]]
}

@test "-o json is the explicit default" {
  merge_on_origin
  run "$PR_LANDED" --output json -C "$TMP/repo" feat
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.ok == true'
}

@test "rejects an unknown --output value as JSON usage error" {
  run "$PR_LANDED" -o yaml -C "$TMP/repo" feat
  [ "$status" -eq 2 ]
  echo "$output" | jq -e '.ok == false and (.error | test("--output must be plain or json"))'
}

@test "-o without a value exits 2 and does not eat the branch" {
  run "$PR_LANDED" -C "$TMP/repo" -o
  [ "$status" -eq 2 ]
  git -C "$TMP/repo" rev-parse --verify -q refs/heads/feat
}
