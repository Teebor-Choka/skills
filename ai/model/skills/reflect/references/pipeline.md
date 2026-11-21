# Pipeline

How a multi-session retrospective is run so it can be repeated and its claims checked.

## Run order

All scripts run with `python3 -I`, read-only on transcripts.

1. `metrics.py scan <folder> > records.jsonl` : one wide record per transcript.
2. `outcomes.py --records records.jsonl --out outcomes.jsonl` : PR states (needs `gh` and network;
   skip it and the north star is withheld).
3. `report.py --records records.jsonl --outcomes outcomes.jsonl --changes reflect/changes.jsonl
--json report.json` : the weekly table. Exit 1 means an alert fired.
4. `scan-sessions.py`, `context-audit.py`, `cost.py`, `drill.py`: the per-lens numbers and
   flagged moments named in SKILL.md.
5. `synthesize.py` over the findings.

Re-running step 1 rebuilds the records from transcripts; a ledger, if the user keeps one, only
caches them.

## Three rounds

1. **By project slice.** One cheap reader per project or time slice reads the flagged moments
   and returns findings in the schema of `friction-signals.md`.
2. **By lens.** One reader per lens (prompts, hooks, cost, skills, orchestration) works across
   all slices, so a pattern that spans projects shows up and a one-project claim is tested.
3. **By theme.** The lead groups findings by mechanism, ranks by recurrence and routes each fix.

### Agent brief

Give each reader: the scope (files, window), the one lens or slice, the output schema, the rule
that every claim carries a session and a line, and the instruction to return compact JSON with
counts, not prose tables. Do not hand a reader your hypothesis; hand it the question.

### Triage table

| Finding               | Check before it enters the ranking                          |
| --------------------- | ----------------------------------------------------------- |
| A count or share      | recompute it from the full set, not a top-N sample          |
| A dollar figure       | name its source (cost state or usage) and window            |
| "X never happens"     | confirm X could have been observed in that transcript       |
| A fix to a named file | run `fixed.py`: last seen before the fix commit means FIXED |

## Verification habit

Every claim from an earlier round is re-checked by a later one and tagged CONFIRMED, REFUTED or
NEW. In the analysis this pipeline came from, round 2 refuted two round-1 claims. A REFUTED claim
is listed as refuted and never ranked.
