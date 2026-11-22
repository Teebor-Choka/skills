# The judge

Paths in this file are relative to the skill directory, except links to sibling reference files.

Per item: an extractor writes the point of the original without its words; the generator writes
the message from the profile and the point; a blind judge call sees TRAIN exemplars and both
messages in seeded random order and names the original; a second call scores the generated one on
the [rubric](rubric.md). Defaults: PASS when the identification rate is within 0.35 to 0.65
and the mean rubric at least 3.5, on at least 20 items. 0.5 means the judge cannot tell; below 0.35
the generated messages overdo the habits (caricature). A judge that
always picks one position, or too many excluded items, makes the round INVALID.

Runners: `--runner claude` (isolated `claude -p`: no tools, no user settings, no session saved),
`--runner cmd:'<command>'` for another harness (prompt on stdin), `--runner stub` for offline
tests. Generator and judge default to the `reasoning` tier, the extractor to `execution`;
`AGENT_TIERS_FILE` maps tiers to models, and `--judge-model` and `--generator-model` take a tier or
a model. In the loop, per-step scoring uses the cheaper `execution` tier (`--score-model`).

Every call's cost lands in `<state>/ledger.jsonl`. `--max-cost-usd X` (both scripts) refuses the
call that would pass `X` with exit 4; sealed runs check the estimate before sealing.
