# Workflow lint hooks

Wire shellcheck, actionlint, and zizmor as commit-time hooks so findings (SC2034, SC2086,
template injection) surface before the commit, not in CI. Snippet for
[git-hooks.nix](https://github.com/cachix/git-hooks.nix) (hook names and default `files` taken
from its `modules/hooks.nix`):

```nix
pre-commit.settings.hooks = {
  # Static check of workflow YAML. Also lints each `run:` block with shellcheck,
  # but only when shellcheck is on its PATH.
  actionlint = {
    enable = true;
    extraPackages = [ pkgs.shellcheck ];
  };
  # Security audit (template injection, unpinned actions, excessive permissions).
  zizmor.enable = true;
  # Standalone shell scripts. Workflow `run:` blocks are covered by actionlint above.
  shellcheck.enable = true;
};
```

- `actionlint` and `zizmor` default to `files = "^.github/workflows/"`, so they only see
  workflows. `shellcheck` matches every shell file by type; narrow it with
  `excludes = [ "^vendor/" ]` if the repo vendors scripts.
- After editing the Nix, re-enter the dev shell so the hooks reinstall, then run
  `pre-commit run --all-files` once to confirm the baseline is clean.
- Without Nix, add local hooks to `.pre-commit-config.yaml` with `language: system` and entries
  `actionlint`, `zizmor --format plain`, and `shellcheck`, scoped by `files:`.
