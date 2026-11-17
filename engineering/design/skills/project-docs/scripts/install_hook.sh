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
# The hook validates the STAGED content of the repo being committed (index exported
# to a temp dir), resolved at commit time, so linked worktrees and unstaged edits
# behave. It never overwrites a symlinked hook, and never writes into a shared
# core.hooksPath outside the target repo: it prints the block to add instead.
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

sh_quote() {
  # POSIX single-quote a string: wrap in '...' and rewrite each ' as '\''.
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

yaml_sq() {
  # YAML single-quoted scalar: wrap in '...' and double each '.
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"
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

# Where the target sits inside its repo ("" at the top, else "sub/dir/"), so a
# subproject is validated, not the whole repo.
SUBDIR=$(git -C "$TARGET_ABS" rev-parse --show-prefix 2>/dev/null || true)

# The block the hook runs. Paths are shell-quoted; the repo is resolved at commit
# time and the staged index is exported to a temp dir, which a subshell trap
# removes. `|| exit` makes a failure abort the commit even when the block is
# prepended before other hook content.
emit_hook_cmd() {
  cat <<EOF
(
  VALIDATOR=$(sh_quote "$VALIDATOR")
  SUBDIR=$(sh_quote "$SUBDIR")
  [ -f "\$VALIDATOR" ] || {
    echo "project-docs: validator not found: \$VALIDATOR (moved or garbage collected); re-run install_hook.sh" >&2
    exit 1
  }
  root=\$(git rev-parse --show-toplevel) || exit \$?
  tmp=\$(mktemp -d) || exit \$?
  trap 'rm -rf "\$tmp"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  name=\$(basename "\$root")
  # export only what the validator reads, not the whole index
  git ls-files -z -- "\${SUBDIR}docs" "\${SUBDIR}AGENTS.md" |
    git checkout-index -z --stdin -f --prefix="\$tmp/\$name/" || exit \$?
  [ -z "\$SUBDIR" ] && mkdir -p "\$tmp/\$name"
  # a subproject with nothing in the index has nothing to validate
  [ -d "\$tmp/\$name/\$SUBDIR" ] || exit 0
  python3 "\$VALIDATOR" "\$tmp/\$name/\$SUBDIR"
) || exit \$?
EOF
}
HOOK_CMD=$(emit_hook_cmd)
BLOCK="$MARKER
$HOOK_CMD
$END_MARKER"

write_managed_hook() {
  # $1 = destination hook file. Insert our marked block after the shebang (so an
  # existing hook that ends in `exit 0` cannot strand it), idempotently.
  dest=$1
  if [ -L "$dest" ]; then
    echo "$dest is a symlink; leaving it (and its target) untouched."
    echo "Add this block to the hook it points to, after the shebang:"
    echo
    printf '%s\n' "$BLOCK"
    return 0
  fi
  block=$BLOCK

  if [ -f "$dest" ] && grep -qF "$MARKER" "$dest" 2>/dev/null; then
    # Replace the managed block in place, so an older install gets upgraded.
    if ! grep -qF "$END_MARKER" "$dest"; then
      echo "error: $dest has the start marker but no end marker; fix it by hand" >&2
      return 1
    fi
    tmp="$dest.project-docs.tmp"
    blockfile="$dest.project-docs.block"
    printf '%s\n' "$block" >"$blockfile"
    awk -v m="$MARKER" -v e="$END_MARKER" -v bf="$blockfile" '
      $0 == m { while ((getline l < bf) > 0) print l; skip = 1; next }
      skip && $0 == e { skip = 0; next }
      !skip { print }' "$dest" >"$tmp"
    rm -f "$blockfile"
    if cmp -s "$tmp" "$dest"; then
      rm -f "$tmp"
      echo "hook already up to date in $dest; nothing to do"
      return 0
    fi
    chmod +x "$tmp"
    mv "$tmp" "$dest"
    echo "updated project-docs pre-commit hook: $dest"
    return 0
  fi

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
        entry: $(yaml_sq "python3 $(sh_quote "$VALIDATOR")")
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
  if [ -n "$(git -C "$TARGET_ABS" config --get core.hooksPath || true)" ]; then
    # A hooks dir outside this repo is shared with other repos: do not write there.
    hp_parent=$(CDPATH='' cd -- "$(dirname -- "$HOOKS_DIR")" 2>/dev/null && pwd -P) ||
      hp_parent=$(dirname -- "$HOOKS_DIR")
    resolved="$hp_parent/$(basename -- "$HOOKS_DIR")"
    top=$(CDPATH='' cd -- "$(git -C "$TARGET_ABS" rev-parse --show-toplevel)" && pwd -P)
    common=$(cd -- "$TARGET_ABS" && CDPATH='' cd -- "$(git rev-parse --git-common-dir)" && pwd -P)
    case "$resolved/" in
    "$top"/* | "$common"/*) ;;
    *)
      echo "core.hooksPath points at $resolved, outside this repository ($top):"
      echo "it may be shared with other repos, so nothing was written."
      echo "Add this block to the pre-commit hook there, after the shebang:"
      echo
      printf '%s\n' "$BLOCK"
      HOOKS_DIR=''
      ;;
    esac
  fi
  if [ -n "$HOOKS_DIR" ]; then
    mkdir -p "$HOOKS_DIR"
    write_managed_hook "$HOOKS_DIR/pre-commit"
  fi
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
  echo "    cp $(sh_quote "$VALIDATOR") ci/validate_docs.py"
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
