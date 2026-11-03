# shellcheck shell=bash
# Sourced, not executed. Shared by rust/hotspots.sh and python/hotspots.sh —
# git-churn logic is identical regardless of language, only the per-file
# complexity source differs (each language's own cognitive.sh output).
#
# Hotspots = touches x complexity, per file. This is the same manual join
# Adam Tornhill's own code-maat documents doing by hand (its README joins a
# `revisions` analysis against a separately-computed complexity source,
# since code-maat itself only measures churn) — no dedicated "hotspots" tool
# exists, so there's nothing to shell out to beyond this join.

# True (exit 0) if <dir> is inside a real, non-shallow git working copy — the
# minimum needed for churn_counts() below to produce meaningful history.
is_churn_capable() {
  local dir="$1"
  git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
  [ "$(git -C "$dir" rev-parse --is-shallow-repository 2>/dev/null)" != "true" ]
}

# Prints per-file commit counts within <dir> as "<count>\t<relative-path>"
# lines, most-touched first, over an optional --since window (all history by
# default).
#
# No default fallback like "100 years ago" here: found by testing directly
# that git's relative-date parser silently returns zero commits for a
# window that large (a real git quirk, not a scripting bug) — omitting
# --since entirely is both simpler and the actually-correct way to mean
# "all history."
#
# --relative matters whenever <dir> is a subdirectory of the actual repo
# root (e.g. a Cargo workspace member) — without it, --name-only reports
# paths relative to the repo root, not <dir>, so a caller joining these
# paths against files under <dir> (as hotspots.sh does) silently matches
# nothing. Found by running this against a real workspace member.
churn_counts() {
  local dir="$1" since="${2:-}"
  local -a since_arg=()
  [ -z "$since" ] || since_arg=(--since="$since")
  git -C "$dir" log "${since_arg[@]}" --relative --name-only --pretty=format: -- . |
    sed '/^$/d' | sort | uniq -c | sort -rn |
    sed -E 's/^[[:space:]]*([0-9]+)[[:space:]]+/\1\t/'
}
