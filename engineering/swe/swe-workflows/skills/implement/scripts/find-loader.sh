#!/usr/bin/env sh
# find-loader.sh — print the path of the `policy` skill's policy_loader.py; exit 1 if none.
#
# The `policy` skill ships in the `harness` plugin (`harness:policy`, `ai/harness` in the same
# marketplace repo); swe-workflows needs it installed.
# Shared by policy-gate.sh and hooks/policy-context.sh. Probe order:
#   1. $AGENTS_POLICY_LOADER (a file path). Set but not a file => exit 1, no fallback.
#   2. skill dirs by skill name: ~/.config/agents/skills, ~/.claude/skills, ~/.agents/skills
#   3. the same repo checkout: <repo>/ai/harness/skills/policy, six levels above this script
#      (<repo>/engineering/swe/swe-workflows/skills/implement/scripts)
#   4. Claude Code plugin cache  ~/.claude/plugins/cache/<marketplace>/harness/<version>/skills/policy
#      (highest version; layout verified against installed plugins)
#   5. Claude Code marketplace checkout ~/.claude/plugins/marketplaces/<marketplace>/ai/harness/skills/policy
#   6. source clone ~/.config/agents/skills-src/public/ai/harness/skills/policy
# Not verified: the Codex and OpenCode plugin layouts for `harness`; use the skill dirs or the override there.
set -eu

if [ -n "${AGENTS_POLICY_LOADER:-}" ]; then
  [ -f "$AGENTS_POLICY_LOADER" ] || exit 1
  printf '%s\n' "$AGENTS_POLICY_LOADER"
  exit 0
fi

for c in \
  "$HOME/.config/agents/skills/policy/policy_loader.py" \
  "$HOME/.claude/skills/policy/policy_loader.py" \
  "$HOME/.agents/skills/policy/policy_loader.py"; do
  [ -f "$c" ] && {
    printf '%s\n' "$c"
    exit 0
  }
done

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
c="$here/../../../../../../ai/harness/skills/policy/policy_loader.py"
[ -f "$c" ] && {
  (CDPATH='' cd -- "$(dirname -- "$c")" && printf '%s/policy_loader.py\n' "$(pwd)")
  exit 0
}

# Newest harness version in the plugin cache. sort -V orders 1.10.0 after 1.9.0.
c=$(for f in "$HOME"/.claude/plugins/cache/*/harness/*/skills/policy/policy_loader.py; do
  [ -f "$f" ] && printf '%s\n' "$f"
done | sort -V | tail -n 1)
[ -n "$c" ] && {
  printf '%s\n' "$c"
  exit 0
}

for c in \
  "$HOME"/.claude/plugins/marketplaces/*/ai/harness/skills/policy/policy_loader.py \
  "$HOME/.config/agents/skills-src/public/ai/harness/skills/policy/policy_loader.py"; do
  [ -f "$c" ] && {
    printf '%s\n' "$c"
    exit 0
  }
done
exit 1
