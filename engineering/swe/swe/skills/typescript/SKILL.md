---
name: typescript
description: >
  Apply TypeScript/JavaScript house rules when editing .ts, .tsx, .js, .jsx, .mjs,
  tsconfig.json or ESLint config, or fixing tsc and eslint errors. Not for Rust or
  audit-only reviews.
license: MIT
compatibility: any
metadata:
  version: "0.1.0"
---

# TypeScript engineer

Enforce TypeScript and JavaScript house standards when creating, modifying, or reviewing
`.ts`/`.tsx`/`.js` files. This is a **starter skill** — it carries the non-negotiable house
rules today and grows an `overrides.md` plus a guidelines index (the way `swe:rust` is
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
  `../rust/overrides.md`): naming, module layout, async, error handling, testing.
- a guidelines index — a curated, ID-addressed reference read on demand, not whole.

See the `models:extension-author` skill for authoring, triggering, and the portability checklist.
