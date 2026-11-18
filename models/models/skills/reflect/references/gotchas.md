# Gotchas

Traps that produced a wrong number or a wrong claim.

- **A compression proxy rewrites tool output.** Text you read through a shell or file tool may
  be shortened or reworded. Read exact bytes with a script when the wording matters (a skill
  description, a quoted line), or say in the report that a proxy was on.
- **Cost state is cumulative, and its key spelling varies.** Take the last value in a segment.
  A drop in the running value is a reset: add the segment's last value and start again.
  `cost.py` reads both `totalCostUsd` and `totalCostUSD`.
- **Do not add subagent cost to a session's cost state.** `metrics.py` reads a session file
  only. Whether the main cost state already includes subagent spend was not settled: a real
  session's cost state was below the price-table total of its main file alone, so the two
  figures cannot be compared. Treat per-session cost as a floor when subagents ran, and never
  sum a main file's cost state with its subagent files.
- **PR links repeat.** A session logs the same link many times. Dedupe on `repo#number` before
  counting; counting events overstated one project's PRs about 35 times.
- **Stop-style hooks fire per turn**, not per session. A hook count is not a session count.
- **The skill listing arrives in pieces and hides descriptions past a size cap.** Merge every
  listing entry; a skill listed by name only cannot be matched on its wording.
- **A synthetic model id is not a model.** It has no price and no cost; ignore it.
- **User-typed correction wording is noise.** "no", "don't", "instead" appear in ordinary
  prose. Count interrupts, denials and bare continue nudges; keep a regex only as a drill-down.
- **A queued, peer or notification entry is not a human prompt**, and an interrupt marker is
  logged as user text. `classify_user_turn` and the interrupt check keep them apart.
- **A gate that exits 1 does not block.** Only exit 2 denies. Metric 4 counts the gate's
  "BLOCK" text arriving as a non-blocking event.
- **Do not build on the harness's own stats cache or usage summary.** They were stale or tiny
  in the analysis this came from. The transcripts are the source.
- **Transcripts can be huge.** Stream line by line; never load a whole file.
