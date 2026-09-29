# Environment skills

Skills for operating inside a particular development environment. Each is a portable Agent Skill
(`SKILL.md`) that runs unchanged on Claude Code, Codex, and OpenCode — see
[skill-creator](../model/tools/skill-creator/SKILL.md) for the cross-agent model.

| Skill                        | What it does                                                                                          | Reach for it when                                                          |
| ---------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [nix](./nix/SKILL.md)        | Work correctly in a Nix + direnv repo — dev-shell entry, `nix fmt` over `cargo fmt`, build traps, and a lightweight pre-commit override | any repo with a `.envrc` or `flake.nix`, on macOS or Linux                 |

`nix` covers the general Nix/direnv dev workflow. Homelab secret injection into hosts and
microVMs is a separate, private concern (a `devops-debug` skill), and the Rust `.rs`/`Cargo.toml`
specifics belong to [rust-engineer](../engineering/swe/rust-engineer/SKILL.md).
