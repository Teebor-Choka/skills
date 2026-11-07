#!/usr/bin/env bash
# Run the static scanners (secrets, dependencies, SAST, CI) on a target and write one result
# file per tool plus summary.tsv. Static stages only: no target code runs, no live endpoint is hit.
# Usage: run-static.sh <target-dir> <out-dir>
# Env:   TRUFFLEHOG_VERIFY=1  let trufflehog test found secrets against the provider APIs (off by default)
set -uo pipefail

target=${1:?usage: run-static.sh <target-dir> <out-dir>}
out=${2:?usage: run-static.sh <target-dir> <out-dir>}
target=$(cd "$target" && pwd) || exit 2
mkdir -p "$out" || exit 2
out=$(cd "$out" && pwd)
summary=$out/summary.tsv
printf 'tool\tstatus\tdetail\n' >"$summary"

# stage <tool> <nixpkgs-attr> <result-file> -- <args...>
# Exit codes 0 and 1 mean "ran" (1 = findings); anything else is a tool error.
stage() {
  local tool=$1 attr=$2 result=$3
  shift 4
  local cmd=("$tool")
  if ! command -v "$tool" >/dev/null 2>&1; then
    command -v nix >/dev/null 2>&1 || {
      printf '%s\tmissing\tnot on PATH and nix unavailable\n' "$tool" >>"$summary"
      return
    }
    cmd=(nix run "nixpkgs#$attr" --)
  fi
  (cd "$target" && "${cmd[@]}" "$@") >"$out/$result" 2>"$out/$tool.stderr"
  local rc=$?
  if [ "$rc" -le 1 ]; then
    printf '%s\tran\texit=%s result=%s\n' "$tool" "$rc" "$result" >>"$summary"
  else
    printf '%s\terror\texit=%s see %s.stderr\n' "$tool" "$rc" "$tool" >>"$summary"
  fi
}

verify=--no-verification
[ "${TRUFFLEHOG_VERIFY:-0}" = 1 ] && verify=--results=verified,unknown

if [ -d "$target/.git" ]; then
  stage gitleaks gitleaks gitleaks.sarif -- git --redact --exit-code 1 \
    --report-format sarif --report-path - --no-banner .
  stage trufflehog trufflehog trufflehog.jsonl -- git "file://$target" --json "$verify"
else
  stage gitleaks gitleaks gitleaks.sarif -- dir --redact --exit-code 1 \
    --report-format sarif --report-path - --no-banner .
  stage trufflehog trufflehog trufflehog.jsonl -- filesystem . --json "$verify"
fi
stage osv-scanner osv-scanner osv.sarif -- scan source -r --format sarif .
stage semgrep semgrep semgrep.sarif -- scan --config p/default --config p/security-audit --metrics=off --sarif --quiet .
if [ -d "$target/.github/workflows" ] || [ -d "$target/.github/actions" ]; then
  stage zizmor zizmor zizmor.sarif -- --format sarif --no-progress .
else
  printf 'zizmor\tskipped\tno .github/workflows\n' >>"$summary"
fi

cat "$summary"
