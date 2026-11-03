#!/usr/bin/env sh
# Wire validate_docs.py into a TARGET project so it runs on commit.
#
# Origin-aware: it joins the hook mechanism the target already uses instead of
# clobbering it.
#   - pre-commit framework (.pre-commit-config.yaml present) -> PRINT the local
#     hook stanza to add (never edits that file: a blind append corrupts the YAML
#     when `repos:` is not the last top-level key).
#   - otherwise a git hook: installed at the dir git actually runs hooks from
#     (`git rev-parse --git-path hooks`), which already accounts for
#     core.hooksPath and the shared common dir of a linked worktree.
# Nix-aware: if the target has a flake.nix, print a checks.<system>.project-docs
# snippet so `nix flake check` gates on the docs too.
# Idempotent: re-running does not duplicate the hook.
#
# Usage: install_hook.sh <target-project>

set -eu

MARKER='# >>> project-docs validate_docs hook >>>'
END_MARKER='# <<< project-docs validate_docs hook <<<'

usage() {
  echo "usage: $0 <target-project>" >&2
  exit 2
}

TARGET=''
for arg in "$@"; do
  case "$arg" in
  -h | --help) usage ;;
  -*)
    echo "unknown option: $arg" >&2
    usage
    ;;
  *)
    if [ -n "$TARGET" ]; then
      echo "error: more than one target given" >&2
      usage
    fi
    TARGET=$arg
    ;;
  esac
done

[ -n "$TARGET" ] || usage
[ -d "$TARGET" ] || {
  echo "error: target project not found: $TARGET" >&2
  exit 2
}

# Resolve the validator's absolute path at install time, so the hook does not
# depend on this script's location later.
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
VALIDATOR="$SCRIPT_DIR/validate_docs.py"
[ -f "$VALIDATOR" ] || {
  echo "error: validator not found next to this script: $VALIDATOR" >&2
  exit 1
}

TARGET_ABS=$(CDPATH='' cd -- "$TARGET" && pwd -P)

# The command the hook runs. Validate the whole project, not just staged files:
# the contract is about the doc tree as a whole. `|| exit` makes a failure abort
# the commit even when the block is prepended before other hook content.
HOOK_CMD="python3 \"$VALIDATOR\" \"$TARGET_ABS\" || exit \$?"

write_managed_hook() {
  # $1 = destination hook file. Insert our marked block after the shebang (so an
  # existing hook that ends in `exit 0` cannot strand it), idempotently.
  dest=$1
  if [ -f "$dest" ] && grep -qF "$MARKER" "$dest" 2>/dev/null; then
    echo "hook already installed in $dest (marker present); nothing to do"
    return 0
  fi

  block="$MARKER
$HOOK_CMD
$END_MARKER"

  if [ ! -f "$dest" ]; then
    printf '#!/usr/bin/env sh\nset -eu\n\n%s\n' "$block" >"$dest"
  else
    tmp="$dest.project-docs.tmp"
    first=$(head -n 1 "$dest")
    case "$first" in
    '#!'*)
      # Keep the existing shebang first; run our check before the rest.
      {
        printf '%s\n' "$first"
        printf '%s\n' "$block"
        tail -n +2 "$dest"
      } >"$tmp"
      ;;
    *)
      {
        printf '#!/usr/bin/env sh\n'
        printf '%s\n' "$block"
        cat "$dest"
      } >"$tmp"
      ;;
    esac
    mv "$tmp" "$dest"
  fi
  chmod +x "$dest"
  echo "installed project-docs pre-commit hook: $dest"
}

# --- (a) pre-commit framework: print only, never edit the YAML ----------------
if [ -f "$TARGET_ABS/.pre-commit-config.yaml" ]; then
  CFG="$TARGET_ABS/.pre-commit-config.yaml"
  if grep -qF 'id: project-docs' "$CFG" 2>/dev/null; then
    echo "pre-commit framework detected; project-docs hook already present in $CFG"
  else
    echo "pre-commit framework detected (.pre-commit-config.yaml)."
    echo "Add this under the existing 'repos:' key (not pasted blindly at EOF):"
    echo
    cat <<EOF
  - repo: local
    hooks:
      - id: project-docs
        name: project-docs contract
        entry: python3 '$VALIDATOR'
        args: ["."]
        language: system
        pass_filenames: false
        always_run: true
EOF
  fi
# --- (b) git hook at the dir git actually uses --------------------------------
elif command -v git >/dev/null 2>&1 && git -C "$TARGET_ABS" rev-parse --git-dir >/dev/null 2>&1; then
  # --git-path hooks resolves core.hooksPath and a worktree's shared common dir,
  # so this is the one place git looks for the hook.
  hooks_rel=$(git -C "$TARGET_ABS" rev-parse --git-path hooks)
  case "$hooks_rel" in
  /*) HOOKS_DIR=$hooks_rel ;;
  *) HOOKS_DIR="$TARGET_ABS/$hooks_rel" ;;
  esac
  mkdir -p "$HOOKS_DIR"
  write_managed_hook "$HOOKS_DIR/pre-commit"
else
  echo "error: $TARGET_ABS has no pre-commit config and is not a git repo;" >&2
  echo "init git first, or run the validator from your CI step directly." >&2
  exit 1
fi

# --- Nix flake note -----------------------------------------------------------
if [ -f "$TARGET_ABS/flake.nix" ]; then
  echo
  echo "flake.nix detected. A git hook is invisible to 'nix flake check'."
  echo "Vendor the validator into the repo (it is stdlib-only), e.g.:"
  echo "    cp \"$VALIDATOR\" ci/validate_docs.py"
  echo "then add a flake check that references the in-tree copy (an absolute"
  echo "out-of-tree path is unreadable in the build sandbox):"
  echo
  cat <<'EOF'
  # inside outputs, per-system (e.g. under flake-utils or your perSystem):
  checks.${system}.project-docs = pkgs.runCommand "project-docs" { } ''
    ${pkgs.python3}/bin/python3 ${./ci/validate_docs.py} ${./.}
    touch $out
  '';
EOF
fi
