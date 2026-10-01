---
name: nix
description: >
  Operate correctly inside Nix + direnv development repos. Use whenever working in a repo
  that has a .envrc or a Nix flake (flake.nix): entering the dev shell, running builds,
  formatting, or editing pre-commit setup, on macOS or Linux. Covers direnv allow per
  worktree, why to format with nix fmt rather than cargo fmt alone, GNU vs BSD sed on macOS,
  the result symlink rotation trap across successive nix build runs, CARGO_BUILD_RUSTFLAGS
  silently replacing .cargo/config.toml rustflags in crane builds, silencing direnv log
  noise, and a lightweight nixpkgs pre-commit override. Trigger even when Nix is incidental
  to a Rust or other change in such a repo. Do not use for homelab secret injection into
  hosts or microVMs, or for authoring application Nix
  modules unrelated to the dev workflow.
license: MIT
compatibility: any
---

# Nix environments

Ground truth for working inside a Nix + direnv repo (a `.envrc` or `flake.nix` at the root),
so shell entry, formatting, and builds work and CI doesn't fail on something that passed
locally.

## Entering the environment

- When a `.envrc` is present, enter the dev shell with `direnv allow <path>` — it works from
  anywhere, so you do not have to be inside the directory first.
- Each git worktree needs its own `direnv allow <worktree-path>` after creation; the parent
  repo's allow does not carry over.
- A fresh worktree does not inherit a `.pre-commit-config.yaml` that is a symlink into the nix
  store — the symlink isn't recreated. Re-create the same symlink in the worktree, or the first
  commit fails with "No .pre-commit-config.yaml file was found."
- Once you're in the environment, invoke commands directly; the tools are on `PATH`.
- Do not bypass the environment with `GIT_DIR`/`GIT_WORK_TREE`. Pre-commit hooks and other
  tooling are wired through the nix shell; bypassing it runs the wrong (or no) hooks.

## Formatting and builds

- Format with `nix fmt`, never `cargo fmt` alone. `cargo fmt --all --check` can pass in CI
  while `nix fmt`'s taplo component still rewrites `Cargo.toml`, leaving CI red on formatting
  you thought was clean.
- On macOS, a nix devshell that provides `gnused` puts GNU `sed` on `PATH` ahead of the system
  BSD `sed`. When you specifically need BSD in-place behavior, call `/usr/bin/sed` explicitly —
  GNU and BSD `sed` disagree on `-i` syntax.

## Build traps

- **Stale `result` symlink.** Each successive `nix build` in the same directory shifts the
  prior `result` to `result-1`, `result-2`, and so on. After building several packages,
  confirm which binary is in which symlink before using it (e.g.
  `strings result/bin/<name> | grep <marker>`) — nix can otherwise serve a stale or cached
  binary silently.
- **Dropped rustflags in crane builds.** `.cargo/config.toml`'s `[build].rustflags` is
  silently discarded by nix package builds (crane / `mkRustPackage`) when the build sets
  `CARGO_BUILD_RUSTFLAGS` — that env var _replaces_, not merges with, config.toml's rustflags.
  Config.toml flags only reach plain non-nix `cargo` and dev shells that re-export them. Concrete
  symptom: a nix-built artifact silently loses `--cfg tokio_unstable` (so tokio-console wiring goes
  dark) even though a local `cargo build` has it. When a `--cfg` or rustflag is not taking effect in
  a nix-built CI job, check this first.
- **`writeShellScriptBin` gets a build-time `bash -n` syntax check** at nix build, so a syntax
  error fails the build rather than the first run. To share a shell library into such a script,
  inline it with `builtins.readFile` — it is spliced at build time and syntax-checked with the
  rest, and leaves no runtime store dependency to resolve.
- **Test a nix-generated script against the built artifact**, on the real target architecture, not
  the source template. Eval-time data (paths, config baked by the derivation) only exists in the
  built output, so the template and the artifact can diverge in exactly the part you need to check.
- **Transient `cache.nixos.org` timeouts during `nix build` are infrastructure, not a code error.**
  Retry before debugging — a failed substituter fetch looks like a build failure but isn't one.

## Flake dev loop and cross-building

- **Iterate a split consumer/modules flake with `--override-input`.** When a consumer flake pulls
  its modules from a separate repo, point the input at a local sibling checkout
  (`--override-input <modules-input> path:../<sibling-checkout>`) so you edit and test without
  committing and re-locking each cycle. Run a fast `nix eval` to catch wiring errors before any
  full build or boot — builds and boots dominate wall-clock by orders of magnitude, so an eval
  that eliminates a wiring bug is far cheaper than the run that would surface it.
- **"Bump the flake" names three distinct operations** — resolve which one before acting:
  update the lock (`nix flake update`), cut a version tag, and rebuild/deploy
  (`darwin-rebuild` / `nixos-rebuild`). They are independent, and the last one changes a live
  machine. Never rebuild or deploy unless explicitly told to.
- **macOS to Linux cross-building goes through a linux-builder VM.** An `aarch64-linux` guest is
  cross-built from an `aarch64-darwin` host via a vfkit/QEMU `linux-builder` VM (QEMU is the
  default hypervisor) whose closure is fetched prebuilt from the official NixOS binary cache, so
  there is no bootstrap chicken-and-egg. The first cross-build is slow; subsequent ones are cached.

## Silencing direnv shell-enter noise

Every command run in a direnv-managed directory re-enters the shell and prints a
`direnv: loading …` / `direnv: export +AR …` banner, which buries real command output and
eats context. Silence it by exporting an empty log format _before_ the direnv hook runs — put
it in `~/.zshenv` (or wherever the parent shell sources its profile):

```sh
export DIRENV_LOG_FORMAT=""
```

Verify by running any command and confirming the output starts with the command's own stdout,
not `direnv: loading …`. A repo-specific banner (a project `shellHook` that `echo`s a header)
is separate — it comes from the nix shell, not direnv, and is gated in the repo's `flake.nix`.

## Lightweight pre-commit override

Stripping heavyweight `nativeCheckInputs` from the nixpkgs `pre-commit` package with an override: read [references/pre-commit-override.md](references/pre-commit-override.md).

## Related skills

- **rust-engineer** covers the `.rs` / `Cargo.toml` specifics and the Rust build sequence
  (including `nix fmt` as its first step); apply it for those. This skill owns the Nix/direnv
  build mechanics — the `result` symlink and crane-rustflags traps live only here.
- **kauki-infra-setup** covers homelab secret injection into hosts and microVMs — a separate,
  private concern that lives inside the kauki.xyz/infra repo, not general dev workflow.
