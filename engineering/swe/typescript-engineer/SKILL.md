---
name: typescript-engineer
description: >
  Enforce TypeScript and JavaScript code quality and house guidelines on every TS/JS
  change. Use whenever writing, modifying, or reviewing a .ts, .tsx, .js, .jsx, or
  .mjs file; configuring tsconfig.json, ESLint, or a bundler; fixing tsc or ESLint
  errors; or adding TypeScript types, modules, or packages. Trigger even when TS/JS is
  only part of a larger multi-language change — the TS/JS portions must still conform.
  Also apply when the user just names TypeScript, JavaScript, tsc, ESLint, Prettier, a
  .ts/.tsx filename, or any TS/JS-specific concept. Do not use for pure after-the-fact
  risk or coverage audits that only report findings (use the code-quality skill), or for
  code in other languages (Rust uses the rust-engineer skill).
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# TypeScript engineer

Enforce TypeScript and JavaScript house standards when creating, modifying, or reviewing
`.ts`/`.tsx`/`.js` files. This is a **starter skill** — it carries the non-negotiable house
rules today and grows an `overrides.md` plus a guidelines index (the way `rust-engineer` is
structured) as real TS/JS work accumulates.

## House rules

- **Compile under `strict`.** `tsconfig.json` sets `"strict": true` (and keep the strict
  family on: `noImplicitAny`, `strictNullChecks`, `noUncheckedIndexedAccess`). Fix the type
  error; do not reach for `any` or `// @ts-ignore` to silence it. When a cast is genuinely
  unavoidable, narrow it and say why.
- **Follow the project's ESLint configuration.** Lint is the house style; fix the finding
  rather than disabling the rule. Disable a rule inline only with a reason comment, and never
  turn a rule down across a whole package to make one call pass.

## Growing this skill

When TS/JS work justifies it, add:

- `overrides.md` — project rules that supersede any base guideline on conflict (mirrors
  `rust-engineer/overrides.md`): naming, module layout, async, error handling, testing.
- a guidelines index — a curated, ID-addressed reference read on demand, not whole.

See the `skill-creator` skill for authoring, triggering, and the portability checklist.
