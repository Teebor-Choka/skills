# shellcheck shell=bash
# Sourced, not executed. Shared by every assets/lang/<language>/tools.sh and by
# assets/run.sh itself — the one place missing_tools() is defined, instead of
# being copy-pasted into every language's tools.sh.

# Prints the subset of the given tool names that are not on PATH, as a JSON
# array (e.g. ["cargo-llvm-cov","cargo-crap"], or [] if all present) — a
# human, CI, or an agent can all parse it the same way. Safe to build by
# hand: tool names are plain identifiers, never containing characters that
# need JSON escaping.
missing_tools() {
  local tool missing=()
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("\"$tool\"")
  done
  local joined=""
  [ "${#missing[@]}" -eq 0 ] || joined="$(
    IFS=,
    echo "${missing[*]}"
  )"
  printf '[%s]' "$joined"
}

# True (exit 0) if <dir> is inside a real, non-shallow git working copy — the
# minimum needed for churn_counts() below to produce meaningful history.
is_churn_capable() {
  local dir="$1"
  git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
  [ "$(git -C "$dir" rev-parse --is-shallow-repository 2>/dev/null)" != "true" ]
}

# Prints per-file commit counts within <dir> as "<count>\t<relative-path>"
# lines, most-touched first, over an optional --since window (all history by
# default). This is the same manual join Adam Tornhill's own code-maat
# documents (its README joins a `revisions` analysis against a
# separately-computed complexity source by hand) — no dedicated "hotspots"
# tool is needed, just this count joined against a language's own
# complexity output.
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

# Runs jscpd against <dir> and prints its console duplication report. Same
# invocation regardless of language — jscpd auto-detects file type by
# extension, so a directory mixing languages gets one combined percentage,
# not a per-language one.
#
# -i excludes .git internals explicitly: jscpd's --no-gitignore default
# (i.e. it DOES respect .gitignore) doesn't help here since a project's own
# .gitignore normally doesn't list .git itself — found by running this
# against a real git-initialized fixture, where jscpd otherwise happily
# scored the shell/perl sample hooks under .git/hooks/*.sample as
# "duplicated bash/perl code," which is noise, not a finding about the
# project.
run_duplication() {
  local dir="$1" tmp_dir
  tmp_dir="$(mktemp -d -t code-quality-measure.XXXXXX)"
  trap 'rm -rf "$tmp_dir"' RETURN
  jscpd "$dir" --reporters console --output "$tmp_dir" --ignore '**/.git/**'
}
