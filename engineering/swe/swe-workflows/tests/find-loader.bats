#!/usr/bin/env bats
# find-loader.sh locates the `policy` skill's policy_loader.py (shipped by the `harness` plugin,
# `harness:policy`). Contract: AGENTS_POLICY_LOADER wins and fails closed; then the skill-dir probes in a
# fixed order; then ai/harness in the same repo checkout; then the Claude Code plugin cache and
# marketplace checkout; then the source clone.

setup() {
  # A copy outside the repo: run in place, the same-repo probe would find this repo's ai/harness.
  mkdir -p "$BATS_TEST_TMPDIR/plugin"
  cp "$BATS_TEST_DIRNAME/../skills/implement/scripts/find-loader.sh" "$BATS_TEST_TMPDIR/plugin/"
  FIND="$BATS_TEST_TMPDIR/plugin/find-loader.sh"
  export HOME="$BATS_TEST_TMPDIR/home"
  mkdir -p "$HOME"
  unset AGENTS_POLICY_LOADER
}

put() { # put <path under $HOME>; creates a loader marked with its own path
  mkdir -p "$HOME/$(dirname "$1")"
  printf '# %s\n' "$1" >"$HOME/$1"
}

@test "nothing installed => exit 1, no output" {
  run sh "$FIND"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
}

@test "AGENTS_POLICY_LOADER pointing at a file wins over every probe" {
  put .config/agents/skills/policy/policy_loader.py
  put elsewhere/loader.py
  AGENTS_POLICY_LOADER="$HOME/elsewhere/loader.py" run sh "$FIND"
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/elsewhere/loader.py" ]
}

@test "AGENTS_POLICY_LOADER pointing at a missing file fails closed, no fallback" {
  put .config/agents/skills/policy/policy_loader.py
  AGENTS_POLICY_LOADER="$HOME/nope.py" run sh "$FIND"
  [ "$status" -eq 1 ]
}

@test "probe order: ~/.config/agents/skills, then ~/.claude/skills, then ~/.agents/skills" {
  put .agents/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.agents/skills/policy/policy_loader.py" ]
  put .claude/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.claude/skills/policy/policy_loader.py" ]
  put .config/agents/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.config/agents/skills/policy/policy_loader.py" ]
}

@test "plugin cache: harness plugin of any marketplace is found" {
  put .claude/plugins/cache/kauki-skills/harness/1.0.0/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$status" -eq 0 ]
  [ "$output" = "$HOME/.claude/plugins/cache/kauki-skills/harness/1.0.0/skills/policy/policy_loader.py" ]
}

@test "plugin cache: highest harness version wins (numeric, not lexical)" {
  put .claude/plugins/cache/kauki-skills/harness/1.9.0/skills/policy/policy_loader.py
  put .claude/plugins/cache/kauki-skills/harness/1.10.0/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.claude/plugins/cache/kauki-skills/harness/1.10.0/skills/policy/policy_loader.py" ]
}

@test "a skill dir beats the plugin cache" {
  put .agents/skills/policy/policy_loader.py
  put .claude/plugins/cache/kauki-skills/harness/1.0.0/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.agents/skills/policy/policy_loader.py" ]
}

@test "a plugin other than harness is ignored" {
  put .claude/plugins/cache/kauki-skills/other/2.0.0/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$status" -eq 1 ]
}

@test "marketplace checkout of the public repo is found" {
  put .claude/plugins/marketplaces/kauki-skills/ai/harness/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.claude/plugins/marketplaces/kauki-skills/ai/harness/skills/policy/policy_loader.py" ]
}

@test "source clone ~/.config/agents/skills-src/public is the last resort" {
  put .config/agents/skills-src/public/ai/harness/skills/policy/policy_loader.py
  run sh "$FIND"
  [ "$output" = "$HOME/.config/agents/skills-src/public/ai/harness/skills/policy/policy_loader.py" ]
}

@test "the same repo checkout: ai/harness six levels above the script is found" {
  scripts="$BATS_TEST_TMPDIR/repo/engineering/swe/swe-workflows/skills/implement/scripts"
  mkdir -p "$scripts" "$BATS_TEST_TMPDIR/repo/ai/harness/skills/policy"
  cp "$FIND" "$scripts/"
  printf '#\n' >"$BATS_TEST_TMPDIR/repo/ai/harness/skills/policy/policy_loader.py"
  put .claude/plugins/cache/kauki-skills/harness/1.0.0/skills/policy/policy_loader.py
  run sh "$scripts/find-loader.sh"
  [ "$status" -eq 0 ]
  [ "$output" = "$(cd "$BATS_TEST_TMPDIR/repo" && pwd)/ai/harness/skills/policy/policy_loader.py" ]
}

@test "a skill dir beats the same repo checkout" {
  scripts="$BATS_TEST_TMPDIR/repo/engineering/swe/swe-workflows/skills/implement/scripts"
  mkdir -p "$scripts" "$BATS_TEST_TMPDIR/repo/ai/harness/skills/policy"
  cp "$FIND" "$scripts/"
  printf '#\n' >"$BATS_TEST_TMPDIR/repo/ai/harness/skills/policy/policy_loader.py"
  put .agents/skills/policy/policy_loader.py
  run sh "$scripts/find-loader.sh"
  [ "$output" = "$HOME/.agents/skills/policy/policy_loader.py" ]
}

@test "the stale sibling public/tools/policy path is not probed" {
  mkdir -p "$BATS_TEST_TMPDIR/layout/repo/engineering/swe/swe-workflows/skills/implement/scripts" "$BATS_TEST_TMPDIR/layout/public/tools/policy"
  cp "$FIND" "$BATS_TEST_TMPDIR/layout/repo/engineering/swe/swe-workflows/skills/implement/scripts/"
  printf '#\n' >"$BATS_TEST_TMPDIR/layout/public/tools/policy/policy_loader.py"
  run sh "$BATS_TEST_TMPDIR/layout/repo/engineering/swe/swe-workflows/skills/implement/scripts/find-loader.sh"
  [ "$status" -eq 1 ]
}
