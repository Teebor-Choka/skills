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
  jscpd "$dir" --reporters console --output "$tmp_dir" --ignore '**/.git/**'
}
