---
name: rust-engineer
description: >
  Enforces Rust code quality and guidelines. Use when writing, modifying, or reviewing
  any .rs file; adding or refactoring Rust modules or crates; fixing Rust compiler
  errors or clippy warnings; working on Cargo.toml dependencies; implementing Rust
  traits, error types, or unsafe blocks; writing Rust tests or benchmarks; or when the
  user mentions Rust, cargo, clippy, rustfmt, a .rs filename, or any Rust-specific
  concept. Apply even when Rust is part of a larger multi-language change — the Rust
  portions must conform to these guidelines.
---

# Rust Development Skill

Enforces Rust coding standards when creating, modifying, or reviewing `.rs` files.

## Process

1. **Read [overrides.md](overrides.md)** — project-specific rules that always take precedence
2. **Write/modify code** conforming to the overrides
3. **Consult [guidelines.txt](guidelines.txt)** only when a specific guideline ID is relevant to the current change (see index below)

## Guidelines Index

Use this table to look up specific sections in `guidelines.txt` when needed.
Do **not** read the entire file — find the relevant ID and read only that section.

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
