# Software-engineering skills

Skills for writing and assessing code. Both are portable Agent Skills (`SKILL.md`) that run on
Claude Code, Codex, and OpenCode.

| Skill                                                 | What it does                                                                                                                               | Reach for it when                                                             |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| [rust-engineer](./rust-engineer/SKILL.md)             | Enforce Rust house guidelines while writing, modifying, or reviewing Rust                                                                  | any `.rs` change, cargo/clippy/rustfmt, traits/unsafe/async, deps             |
| [code-quality](./code-quality/SKILL.md)               | Audit code risk from complexity, coverage, duplication, and structural metrics plus comment quality, verifying each finding (reports only) | "is this PR safe to merge?", "how risky is this?", auditing AI-generated code |
| [review-gauntlet](./review-gauntlet/SKILL.md)         | Run a block of build work through red-first roles and a read-only four-angle review gauntlet that reports findings without editing.        |
| [typescript-engineer](./typescript-engineer/SKILL.md) | Enforce TypeScript and JavaScript code quality and house guidelines on every TS/JS change.                                                 |

They pair cleanly: **code-quality finds and reports** (it never edits code); **rust-engineer**
(or another language engineering skill) **fixes**. code-quality runs its measure and
comment-quality passes as a workflow — see its `references/cross-agent.md` for native dispatch
on each agent.
