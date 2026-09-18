---
name: rust-engineer
description: >
  Enforce Rust code quality and house guidelines on every Rust change. Use whenever
  writing, modifying, or reviewing a .rs file; adding or refactoring Rust modules or
  crates; fixing rustc errors or clippy warnings; running cargo, clippy, or rustfmt;
  implementing traits, error types, async, or unsafe blocks; editing Cargo.toml
  dependencies or features; or writing Rust tests or benchmarks. Trigger even when Rust
  is only part of a larger multi-language change — the Rust portions must still conform.
  Also apply when the user just names Rust, cargo, clippy, rustfmt, a .rs filename, or
  any Rust-specific concept. Do not use for pure after-the-fact risk, complexity, or
  test-coverage audits that only report findings without changing code (use the
  code-quality skill), or for code in other languages.
---

# Rust engineer

Enforce Rust coding standards when creating, modifying, or reviewing `.rs` files. Two
knowledge sources back this skill, layered so project intent always wins:

- `overrides.md` — this project's rules; they **supersede** the base guidelines on conflict.
- `guidelines.txt` — the Pragmatic Rust Guidelines, addressed by ID (see the index).

## Process

1. **Read [overrides.md](overrides.md) first.** These project rules take precedence, so
   applying them before anything else avoids writing code you then have to redo.
2. **Write or modify the code** to conform to the overrides.
3. **Consult [guidelines.txt](guidelines.txt) by ID only when relevant.** The file is large;
   loading it whole wastes context and buries the rule that matters. Find the guideline ID
   for the concept at hand in the index below, then read only that section.

For a large multi-file or multi-crate refactor, delegate the mechanical fan-out to your
agent's subagents — each still applying this skill to its slice — while you keep the design
decisions. This skill's `SKILL.md` loads the same on Claude Code, Codex, and OpenCode; for
how to wire subagents, commands, or hooks per agent, see the `skill-creator` skill.

## Guidelines index

Look up sections in `guidelines.txt` here. Do **not** read the whole file — find the
relevant ID and read only that section.

| Category              | Guideline IDs                                                                                                                                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **AI & Design**       | `M-DESIGN-FOR-AI`                                                                                                                                                                                                                                      |
| **Applications**      | `M-APP-ERROR`, `M-MIMALLOC-APPS`                                                                                                                                                                                                                       |
| **Documentation**     | `M-CANONICAL-DOCS`, `M-DOC-INLINE`, `M-FIRST-DOC-SENTENCE`, `M-MODULE-DOCS`                                                                                                                                                                            |
| **FFI**               | `M-ISOLATE-DLL-STATE`                                                                                                                                                                                                                                  |
| **Performance**       | `M-HOTPATH`, `M-THROUGHPUT`, `M-YIELD-POINTS`                                                                                                                                                                                                          |
| **Safety**            | `M-UNSAFE-IMPLIES-UB`, `M-UNSAFE`, `M-UNSOUND`                                                                                                                                                                                                         |
| **Universal**         | `M-CONCISE-NAMES`, `M-DOCUMENTED-MAGIC`, `M-LINT-OVERRIDE-EXPECT`, `M-LOG-STRUCTURED`, `M-PANIC-IS-STOP`, `M-PANIC-ON-BUG`, `M-PUBLIC-DEBUG`, `M-PUBLIC-DISPLAY`, `M-REGULAR-FN`, `M-SMALLER-CRATES`, `M-STATIC-VERIFICATION`, `M-UPSTREAM-GUIDELINES` |
| **Libs / Building**   | `M-FEATURES-ADDITIVE`, `M-OOBE`, `M-SYS-CRATES`                                                                                                                                                                                                        |
| **Libs / Interop**    | `M-DONT-LEAK-TYPES`, `M-ESCAPE-HATCHES`, `M-TYPES-SEND`                                                                                                                                                                                                |
| **Libs / Resilience** | `M-AVOID-STATICS`, `M-MOCKABLE-SYSCALLS`, `M-NO-GLOB-REEXPORTS`, `M-STRONG-TYPES`, `M-TEST-UTIL`                                                                                                                                                       |
| **Libs / UX**         | `M-AVOID-WRAPPERS`, `M-DI-HIERARCHY`, `M-ERRORS-CANONICAL-STRUCTS`, `M-ESSENTIAL-FN-INHERENT`, `M-IMPL-ASREF`, `M-IMPL-IO`, `M-IMPL-RANGEBOUNDS`, `M-INIT-BUILDER`, `M-INIT-CASCADED`, `M-SERVICES-CLONE`, `M-SIMPLE-ABSTRACTIONS`                     |
