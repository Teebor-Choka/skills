# Review a deck (the linter)

Beyond looking patterns up, this skill can **score an actual deck against them** —
a unit-test suite for a presentation. It ingests a `.pptx`/`.pdf` (via the sibling
`deck-io/` library), runs one check per pattern, and reports conformance + fixes.

```sh
cd communication/presentation/skills/patterns/scripts
nix shell nixpkgs#nodejs --command node review.mjs <deck.pptx> [--plan <deck>.plan.yaml] [--json] [--fix]
```

- **Headline conformance** is artifact-derived only (deterministic + animation deck
  checks) — reproducible, ungameable. **plan-presence** (`<deck>.plan.yaml` fields
  like `big_why`, `rehearsal_count`) is a reported checklist; **LLM-tier** checks are
  emitted as `llm_jobs` for _you (the agent)_ to judge against the slide text/notes
  and fold in as advisory — never in the headline. ~14 pure live-delivery patterns
  are listed as unscoreable.
- `--fix` applies safe pptx fixes (raise sub-min fonts, strip master logo) to a
  `*.fixed.pptx` copy.
- `scripts/registry.mjs` maps all 88 patterns → tier → check, and which phase each
  tier lands in.
