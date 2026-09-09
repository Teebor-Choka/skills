# shellcheck shell=bash
# Sourced, not executed. Shared by rust/duplication.sh and
# python/duplication.sh — jscpd isn't Rust- or Python-specific, so there's
# nothing language-specific about running it.

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
  jscpd "$dir" --reporters json --output "$tmp_dir" --ignore '**/.git/**' >/dev/null 2>&1 || true
  if [ -f "$tmp_dir/jscpd-report.json" ]; then
    cat "$tmp_dir/jscpd-report.json"
  else
    echo '{"statistics":{"formats":{},"total":{"format":"total","clones":0,"duplicatedLines":0,"duplicatedTokens":0,"lines":0,"percentage":0,"percentageTokens":0,"sources":0,"tokens":0}}}'
  fi
}

# Runs jscpd and reshapes it straight into this metric's canonical envelope
# (see ../_common.sh's emit_json) — identical reshaping regardless of
# language, so run.sh's two duplication.sh callers are each a one-line call
# to this rather than repeating the same jq filter twice.
emit_duplication_json() {
  local language="$1" dir="$2" raw
  raw="$(run_duplication "$dir")"
  jq -n --arg language "$language" --argjson raw "$raw" '{
    metric: "duplication",
    language: $language,
    unit: "percent",
    threshold: null,
    rows: [$raw.statistics.formats | to_entries[] | {format: .key} + .value],
    summary: $raw.statistics.total
  }'
}
