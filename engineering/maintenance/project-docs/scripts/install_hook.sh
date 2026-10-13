#!/usr/bin/env sh
# Wire validate_docs.py into a TARGET repo so it runs on commit.
#
# Origin-aware: it detects how the target already manages hooks and joins that
# mechanism instead of clobbering it.
#   a) pre-commit framework (.pre-commit-config.yaml present) -> print the local
#      hook stanza to add; append it only with --write.
#   b) plain hooks via `git config core.hooksPath <dir>` -> install a pre-commit
#      hook in that dir.
#   c) neither -> install .git/hooks/pre-commit, appending if one exists.
# Nix-aware: if the target has a flake.nix, print a checks.<system>.repo-docs
# snippet so `nix flake check` gates on the docs too.
# Idempotent: re-running does not duplicate the hook.
#
# Usage: install_hook.sh <target-repo> [--write]

set -eu

MARKER='# >>> repo-docs validate_docs hook >>>'
END_MARKER='# <<< repo-docs validate_docs hook <<<'

usage() {
  echo "usage: $0 <target-repo> [--write]" >&2
  exit 2
}

WRITE=0
TARGET=''
for arg in "$@"; do
  case "$arg" in
  --write) WRITE=1 ;;
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
  echo "error: target repo not found: $TARGET" >&2
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

# The command the hook runs. Validate the whole target repo, not just staged
# files: the contract is about the repo's doc tree as a whole.
HOOK_CMD="python3 \"$VALIDATOR\" \"$TARGET_ABS\""

write_managed_hook() {
  # $1 = destination hook file. Create or append our marked block, idempotently.
  dest=$1
  if [ -f "$dest" ] && grep -qF "$MARKER" "$dest" 2>/dev/null; then
    echo "hook already installed in $dest (marker present); nothing to do"
    return 0
  fi
  if [ ! -f "$dest" ]; then
    printf '#!/usr/bin/env sh\nset -eu\n\n' >"$dest"
  fi
  {
    echo "$MARKER"
    echo "$HOOK_CMD"
    echo "$END_MARKER"
  } >>"$dest"
  chmod +x "$dest"
  echo "installed repo-docs pre-commit hook: $dest"
}

# --- (a) pre-commit framework -------------------------------------------------
if [ -f "$TARGET_ABS/.pre-commit-config.yaml" ]; then
  STANZA=$(
    cat <<EOF
  - repo: local
    hooks:
      - id: repo-docs
        name: repo-docs contract
        entry: python3 $VALIDATOR
        language: system
        pass_filenames: false
        always_run: true
EOF
  )
  CFG="$TARGET_ABS/.pre-commit-config.yaml"
  if grep -qF 'id: repo-docs' "$CFG" 2>/dev/null; then
    echo "pre-commit framework detected; repo-docs hook already present in $CFG"
  elif [ "$WRITE" -eq 1 ]; then
    printf '%s\n' "$STANZA" >>"$CFG"
    echo "appended repo-docs local hook to $CFG"
    echo "note: verify it sits under an existing 'repos:' key; re-indent if your config nests differently."
  else
    echo "pre-commit framework detected (.pre-commit-config.yaml)."
    echo "Add this under 'repos:' (or re-run with --write to append it):"
    echo
    printf '%s\n' "$STANZA"
  fi
else
  # --- (b) core.hooksPath ---------------------------------------------------
  HOOKS_PATH=''
  if command -v git >/dev/null 2>&1; then
    HOOKS_PATH=$(git -C "$TARGET_ABS" config --get core.hooksPath 2>/dev/null || true)
  fi
  if [ -n "$HOOKS_PATH" ]; then
    case "$HOOKS_PATH" in
    /*) HOOKS_DIR=$HOOKS_PATH ;;
    *) HOOKS_DIR="$TARGET_ABS/$HOOKS_PATH" ;;
    esac
    mkdir -p "$HOOKS_DIR"
    write_managed_hook "$HOOKS_DIR/pre-commit"
  else
    # --- (c) plain .git/hooks ---------------------------------------------
    GITDIR="$TARGET_ABS/.git"
    if [ -f "$GITDIR" ]; then
      # worktree or submodule: .git is a file pointing at the real gitdir.
      REAL=$(sed -n 's/^gitdir: //p' "$GITDIR" 2>/dev/null || true)
      case "$REAL" in
      /*) GITDIR=$REAL ;;
      ?*) GITDIR="$TARGET_ABS/$REAL" ;;
      esac
    fi
    if [ ! -d "$GITDIR" ]; then
      echo "error: $TARGET_ABS is not a git repo (no .git); cannot install a git hook" >&2
      echo "init git first, or add the validator to your CI step directly." >&2
      exit 1
    fi
    mkdir -p "$GITDIR/hooks"
    write_managed_hook "$GITDIR/hooks/pre-commit"
  fi
fi

# --- Nix flake note -----------------------------------------------------------
if [ -f "$TARGET_ABS/flake.nix" ]; then
  echo
  echo "flake.nix detected. A git hook is invisible to 'nix flake check'."
  echo "Add the validator as a flake check so CI gates on it too, e.g.:"
  echo
  cat <<EOF
  # inside outputs, per-system (e.g. under flake-utils or your perSystem):
  checks.\${system}.repo-docs = pkgs.runCommand "repo-docs" { } ''
    \${pkgs.python3}/bin/python3 ${VALIDATOR} \${./.}
    touch \$out
  '';
EOF
fi
