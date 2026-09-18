# Sources

This skill is pooled and deduplicated from the main open "unslop" (de-AI-writing) agent
skills on GitHub, plus the research they cite. It is a synthesis, not a fork of any one.

## Skills pooled

- **cursor/plugins** — `pstack/skills/unslop`, the canonical base: 33 stably-numbered
  rules most others descend from, and the cleanest jargon-noun to concrete mapping.
  Surfaced via https://www.ui-skills.com/skills/cursor/unslop
- **theclaymethod/unslop** (446★) — the most engineered: a 36-category taboo catalog with
  per-entry detection regex, a discourse-level "silhouette" scanner, and an eval harness.
  https://github.com/theclaymethod/unslop
- **MohamedAbdallah-14/unslop** (140★) — deepest research grounding: intensity levels,
  a warmth/reliability tradeoff, anti-detector context, and a calibrated-uncertainty
  ladder. https://github.com/MohamedAbdallah-14/unslop
- **asavvin-pixel/unslop** (67★) — the three-level model (typography, vocabulary,
  structure), the outline test, the epistemics contract, and the "clean slop" layer,
  with Paul Graham prose benchmarks. https://github.com/asavvin-pixel/unslop
- **woerndl/unsloppify** (19★) — best for agentic coding output: process leakage, agent
  handoff over-structuring, generic benefit tails, and a portable regex list.
  https://github.com/woerndl/unsloppify
- **badmuriss/unslop** (18★) — the StoryScope narrative layer, per-model fingerprints,
  five operational modes, and a factual-integrity invariant. https://github.com/badmuriss/unslop
- **mnapoli/skills** (13★) — a faithful pstack derivative that fills in missing rules and
  expands the jargon-noun and plain-speech sets. https://github.com/mnapoli/skills
- **mshumer/unslop** (549★) — a generator that emits a domain-specific skill rather than a
  static list; contributes the per-domain-calibration idea. https://github.com/mshumer/unslop

## Research and style references

- Wikipedia, "Signs of AI writing" (WikiProject AI Cleanup) — the surface taxonomy
  backbone. https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- UMD / Google DeepMind study (2026), 61,608 texts — structural features barely drop after
  cliché removal (95.5% to 93.9% detection).
- Russell, Rajendhran, Pham, Iyyer & Wieting, "StoryScope: Investigating Idiosyncrasies in
  AI Fiction," arXiv:2604.03136. https://github.com/jenna-russell/storyscope
- Berens & Kobak, "Delving into ChatGPT usage in academic writing," Science Advances
  (2024) — excess-word frequency over 14M PubMed abstracts.
  https://github.com/berenslab/llm-excess-vocab
- Google developer documentation style guide and word list.
  https://developers.google.com/style and https://developers.google.com/style/word-list
- hardikpandya/stop-slop — false-agency signal source. https://github.com/hardikpandya/stop-slop
- Paul Graham essays (Good Writing, The Best Essay, and others) — prose benchmarks.

## Standing caveat

Every source stresses the same point: lexical tells decay per model generation while the
structural habits persist. Treat the word and phrase lists as dated hints and put the
weight on the structural pass.
