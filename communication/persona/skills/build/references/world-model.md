# build: the predictive world-model loop

Intent: learn a persona the way a forecaster learns. Before the model sees the next message, it
predicts what the person will write from the map it has built so far. The gap between the
prediction and the actual message drives a small patch to the map. The map is a structured world
model of the person (beliefs, decision rules, reactions, format rules per band and channel,
lexicon), not a pile of samples. Every item is predicted before it is seen, so the curve of
surprise over the stream measures learning without leakage. A sealed slice that the loop never
touches gives the final verdict once, with the map frozen.

`world.py` is the default build path. The fold-based profile loop of [spec.md](spec.md) is the
legacy path; both share ingest, split, the extractor, the judge prompts and the report math.

## Pipeline

```
samples ─ ingest.py ─▶ corpus.jsonl ─ split.py ─▶ train / test (test = the sealed slice)
world.py init      ─▶ stream.json (train ids in stream order), empty map.json, state.json
world.py run       ─▶ per item: EXTRACT ─ PREDICT ─ SCORE ─ UPDATE (─ CONSOLIDATE every N)
                      map.json, map.md, log.jsonl, curve.json, ledger.jsonl, state.json
world.py final     ─▶ final/report.{json,md} on the sealed slice, once, frozen map
map.md ─▶ write (drafting as the persona)
```

Python 3.13, stdlib only, deterministic for a given input, seed and runner, offline except the
`claude` runner. State dir and guard are the ones in [spec.md](spec.md) and
[privacy.md](privacy.md): never inside a path a git work tree would track (exit 3).

## Commands

```
world.py init     --persona P [--seed S] [--force]
world.py run      --persona P --runner R [--max-steps N] [--max-cost-usd X] [--resume]
world.py cost-estimate --persona P --runner R --steps N [--max-cost-usd X]
world.py status   --persona P
world.py final    --persona P --runner R [--max-cost-usd X] [--rerun-test REASON]
world.py render   --persona P
world.py validate --persona P
```

Runners as in [spec.md](spec.md): `claude`, `cmd:'<command>'`, `stub` (with `--stub-script`).
Model flags take a tier or a model: `--extract-model` (default `execution`), `--predict-model`
(`reasoning`), `--score-model` (`execution`, the cheaper tier for per-step scoring),
`--update-model` and `--consolidate-model` (`reasoning`), and for `final` `--generator-model`
and `--judge-model` (`reasoning`). Loop knobs: `--threshold` (0.3), `--window` (20),
`--consolidate-every` (10), `--max-nodes` (120), `--max-map-bytes` (16384), `--exemplars` (4),
`--seed` (for `init` the stream seed, default the split seed; for `run` the judge's position
seed, default 1337). Budget: `--max-cost-usd`, `--call-estimate-usd` (0.50).

The first `run` pins the models and loop knobs (all but `--window`) in `state.json`. Later runs
fill unset flags from there; a flag that differs from the pinned value exits 2, so a resumed run
cannot drift. `validate` checks against the pinned caps.

## Stream and sealed slice

- `init` reads the split (`split.py` must have run). The stream is the TRAIN items. The order is
  chronological when every item's `ts` parses (ISO 8601, else RFC 2822; naive times count as
  UTC; ties keep corpus order); otherwise a shuffle seeded by `--seed` (default: the split seed).
  `stream.json` records the ids, the order (`chronological` or `seeded`), the seed, the reason
  for a fallback, the split id and the sealed ids. It holds no message text.
- The sealed slice is the split's test slice (`test.jsonl`). It is never ingested into the
  stream, never shown to predict, score or update, and judged once by `final`.
- As a second line of defence, `init` drops from the stream any item that is a near duplicate
  (`NEAR_DUP`) of a sealed item and records the count; split already prevents this.
- A context that quotes or nearly repeats a later stream item (a `reply_to` chain read out of
  order, which a seeded order can produce) would show the predictor that item early. `init`
  lists such items in `redacted_contexts`; `run` and `final` blank their context.
- `run` and `final` refuse (exit 2) when the split's id no longer matches `stream.json` (a
  re-split happened): start over with `init --force`.

## One step

Step `i` handles stream item `x_i`. Calls are tagged with the step in the ledger.

1. **EXTRACT.** The extractor of `evaluate.py` writes the point, intent and context of `x_i`
   without its words, with the same point-leak check and one strict retry. On a second failure
   the step is `excluded` (`point_leak` or `error`): it gets no prediction and no score, is not on
   the curve, and still goes to UPDATE as an unscored item (the map learns from it; surprise is
   `null`).
2. **PREDICT.** The predictor sees `map.md`, the item's channel, audience, context, point and
   intent. It never sees `x_i`'s text or band, any later stream item, or any sealed item. A prediction that `copied()` the actual is a leak: the step is excluded as `copied`.
3. **SCORE.** The blind pairwise pick of `evaluate.py` (`identify_prompt`, seeded position) and its
   rubric (`score_prompt`) compare the prediction with the actual. The judge's exemplars come
   only from the stream items before `i`, so the curve stays prequential. The rubric call also
   returns `missed`, a subset of `format`, `length`, `content`, `belief`, `reaction`,
   `vocabulary`, and `entities`, the named people, projects, places and products the actual
   mentions. Surprise:

   ```
   hit_i      = 0 when the judge was fooled, 1 when it picked the actual or gave no valid pick
   rubric_i   = mean of the five rubric dimensions, 0..5 (an unparseable reply scores 0)
   surprise_i = 0.5 * hit_i + 0.5 * (1 - rubric_i / 5)          in [0, 1]
   ```

4. **UPDATE.** Runs when `surprise_i >= threshold`, or the item is new: the map is empty, the
   judge lists `belief` as missed, or an entity the judge named appears in no node text, or the
   step was excluded. Otherwise it is skipped (`skip: low_surprise`). The updater sees `map.json`,
   the actual, the prediction, the scores, `missed` and the judge's reasons, and returns
   `{"patches": [...]}`. Each patch is validated against the map and applied on its own; a bad
   patch is rejected with a reason in the log and the rest still apply.
5. **CONSOLIDATE.** Every `--consolidate-every` steps, and in any step where an `add` was
   rejected for the cap, the consolidator sees `map.json` and returns patches that merge
   duplicates and drop weak nodes, aiming at 80% of the cap. Afterwards, if the map is still over
   that target (in nodes, or `map.md` over 80% of `max_map_bytes`), a deterministic prune removes
   nodes by lowest confidence, then fewest evidence ids, then oldest update, then id, until it
   fits. The cap therefore holds, and room for new nodes returns, even when the consolidator
   returns garbage.
6. **CHECKPOINT.** See Resume.

## Map schema (`map.json`)

```
{"version": 1, "persona": str, "step": int,           # steps applied
 "nodes": [node...], "edges": [edge...]}
node = {"id": slug, "type": TYPE, "text": str (1..280 chars), "confidence": 0..1,
        "evidence": [item id...] (1+, every id an already-seen stream item),
        "band": "short"|"long"|"any", "channel": str,   # format_rule only, both required
        "created": step, "updated": step}
edge = {"from": node id, "to": node id, "type": "supports"|"applies-to"}
TYPE = entity | belief | decision_rule | reaction_pattern | format_rule | lexicon | never_do
slug = ^[a-z0-9][a-z0-9-]{0,47}$
```

Constraints: unique node ids; edges join two existing, distinct nodes; no duplicate edge;
`len(nodes) <= max_nodes`, `len(edges) <= 2 * max_nodes`; the rendered `map.md` is at most
`max_map_bytes`. `world.py validate` checks all of this and prints `valid` or the errors (exit 2).

Patches (the updater and the consolidator use the same set):

| op            | fields                                    | effect                                             |
| ------------- | ----------------------------------------- | -------------------------------------------------- |
| `add`         | `node` (id, type, text, confidence?, ...) | new node; confidence defaults to 0.5               |
| `strengthen`  | `id`, `by?` (default 0.1)                 | confidence up, capped at 1                         |
| `weaken`      | `id`, `by?` (default 0.1)                 | confidence down, floored at 0                      |
| `revise`      | `id`, `text`, `confidence?`               | new text                                           |
| `remove`      | `id`                                      | node and its edges removed                         |
| `merge`       | `ids` (2+), `into` (a node)               | one node with the union of evidence; edges rewired |
| `add_edge`    | `edge`                                    | new edge                                           |
| `remove_edge` | `edge`                                    | edge removed                                       |

The current item id is added to the evidence of every node a patch adds or changes. Evidence ids a
patch names must be stream items already seen (`stream[0..i]`); any other id, including a sealed
or a future id, rejects the patch. An `add` past `max_nodes`, a duplicate id, an unknown op, type,
node or edge, a bad slug, text out of length, or a confidence outside `[0, 1]` rejects the patch.
A reply carries at most 24 patches; the rest are rejected. Consolidation may not `add`, and adds
no evidence (it sees no item). The predictor is not told the length band: format is learned like
any other rule.

## Files in the state dir

| File           | Content                                                                                                                                                                 |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `stream.json`  | order, seed, split id, stream ids, sealed ids, dropped near duplicates                                                                                                  |
| `map.json`     | the map above                                                                                                                                                           |
| `map.md`       | `render` of `map.json`: deterministic, no timestamps; what `write` loads                                                                                                |
| `log.jsonl`    | one row per step: item, band, channel, excluded, prediction, pick, scores, rubric, hit, surprise, missed, new, update or skip, applied and rejected patches, node count |
| `curve.json`   | rolling-window id rate, rubric and surprise per scored step, first and last window                                                                                      |
| `state.json`   | `next` (index of the next step), `map_hash`, `ledger_total`, `steps_total`                                                                                              |
| `ledger.jsonl` | one row per model call: ts, tool, role, model, cost_usd, input and output tokens, step                                                                                  |
| `final/`       | `items.jsonl`, `report.json`, `report.md` of the sealed run                                                                                                             |

`map.md` lists, in this order, Entities, Beliefs, Decision rules, Reaction patterns, Format rules
(grouped by band, then channel), Lexicon, Never do, and Edges; nodes sorted by confidence
(descending), then id. Same `map.json`, same bytes.

## Curve and final report

- Curve: over scored (non-excluded) steps in stream order, point `k` is the mean of `hit` and of
  `rubric` and of `surprise` over the last `window` scored steps up to `k` (fewer at the start).
  `first` and `last` are the first full window and the last window. An id rate falling toward 0.5
  and a rubric rising is learning.
- `final` needs a finished loop (`next == len(stream)`, exit 2 otherwise). It renders the frozen
  map, records its hash, seals `split/test.sealed` (shared with `evaluate.py`: a used slice is
  used, whichever tool used it; a second run needs `--rerun-test REASON`), then runs
  `evaluate.py`'s `run_item` on every sealed item with `map.md` as the profile and the stream as
  exemplars. The report is `summarize()`: verdict, id rate, rubric, per band and per channel with
  their verdicts, plus the curve's first and last window and the cost (ledger total, by role,
  loop and final).

## Budget guard

- Every runner reports `(text, usage)`. The `claude` runner adds `--output-format json` and reads
  `result`, `is_error`, `subtype`, `total_cost_usd` and `usage.input_tokens`,
  `usage.output_tokens` (plus `cache_creation_input_tokens` and `cache_read_input_tokens` into
  input). `is_error: true` or a subtype other than `success` is a failed call. For the `claude`
  runner any other stdout is a failed call too (fail closed). A `cmd:` runner whose stdout is
  such a JSON object is read the same way; plain text is the reply with unknown cost.
- A command runner makes up to 2 attempts per call. Every paid attempt appends a row to
  `<state>/ledger.jsonl` (also for `evaluate.py`), failed ones included. An attempt of unknown
  cost (a timeout, plain text, a call killed mid-flight) is charged one call's estimate, never 0,
  and flagged `estimated`.
- Estimate for the next call: 1.5 times the largest cost seen for the same role and model, or 1.5
  times that role and model's largest cost per prompt character times this prompt's length,
  whichever is larger; with no history `--call-estimate-usd` (default 0.50).
- With `--max-cost-usd X`, before each call the guard re-reads the ledger (so another process's
  spend on the same state dir counts) and reserves the estimate times the runner's attempts under
  a lock (so parallel `--jobs` cannot overshoot together). It refuses when ledger total plus
  reservations plus that exceeds `X`: exit 4, `budget: ...` on stderr, nothing of the current
  step committed. The run resumes with a higher cap. Reservations are per process: two processes
  started together can each pass the check once.
- Before sealing, `final` and `evaluate.py --slice test` refuse (exit 4, seal untouched) when the
  ledger total plus items times the per-item estimate (2 attempts of each call, the extractor's
  retry included) exceeds the cap. If the cap still stops a sealed run, no result is written and
  the run is marked `aborted` in `test.sealed`: it does not use up the slice, and the next run
  needs no `--rerun-test`.
- `cost-estimate --steps N` runs up to N real steps (they count; `run --resume` continues after
  them), then prints the mean and maximum cost per step, the projected total for the remaining
  stream (consolidations only at the rate they occurred in the sampled steps), and the projected final from the per-role means at the final's
  models (a lower bound when the final uses a stronger tier than the steps; it says so).
- Stub runners take costs from the script (`cost` per role, `cost_default`), so tests cover the
  guard.

## Resume

- After each step: write `map.next.json` atomically, then `state.json` atomically with
  `next = i + 1` and the new map hash, then rename `map.next.json` to `map.json`, render
  `map.md`, rewrite `curve.json`. A log row for step `i` is appended before `state.json`.
- On start: a `map.next.json` whose hash equals `state.map_hash` is renamed into place (a crash
  after the state commit); any other `map.next.json` is deleted. `log.jsonl` rows with
  `step >= next` are dropped. A `map.json` whose hash differs from `state.map_hash` is an error
  (exit 2): the map was edited by hand. A torn last line of `log.jsonl` is dropped. `map.md` and
  `curve.json` are rewritten from the checkpoint.
- A crash or a budget stop mid-step therefore repeats only that step, and a resumed run gives the
  same `map.json` and `log.jsonl` bytes as an uninterrupted one. The ledger is append-only: money
  spent on an aborted step stays recorded.
- `run` without `--resume` after a step was committed exits 2. A lock file stops two runs on one
  persona (exit 2); `init` takes the same lock.

## Failure

| Condition                                              | Behaviour                               |
| ------------------------------------------------------ | --------------------------------------- |
| state dir tracked by git                               | exit 3, nothing written                 |
| no split, no init, split changed since init            | exit 2 naming the step                  |
| `init` twice without `--force`                         | exit 2                                  |
| `run` after a commit without `--resume`; second runner | exit 2                                  |
| `map.json` edited outside `world.py`                   | exit 2                                  |
| budget cap would be passed                             | exit 4, last checkpoint kept            |
| extract fails twice or leaks                           | step excluded, unscored update          |
| bad patch                                              | rejected with reason in the log         |
| update or consolidate reply unparseable or fails twice | no patches; logged; the cap still holds |
| `final` before the loop ends; second `final`           | exit 2 (second: needs `--rerun-test`)   |

## AI-gap closed

"An agent built this, every test passed, and it still behaved wrong":

- The predictor sees the actual through the point, the map or the exemplars: closed by the
  extractor's leak check, the update running after the prediction, past-only exemplars, and a
  canary test over every prompt.
- The map learns the sealed slice: closed by the stream holding only TRAIN ids, evidence ids
  limited to seen items, and a canary test.
- A resumed run double-applies a step: closed by the paired atomic commit and the byte-identical
  resume test.
- The cap leaks under parallel calls or unknown costs: closed by reservations and charging the
  estimate.
- A budget stop burns the sealed slice: closed by the preflight before the seal and the aborted
  run that does not count as a use.
- A reply-to context carries a later message into an early prompt: closed by `redacted_contexts`.

## Acceptance tests

Offline, stub runners, in `tests/test_persona_world_*.py`:

- [ ] AT-W1 stream: chronological when every ts parses (ISO and RFC 2822 mixed), seeded and
      recorded otherwise, same seed same order; no sealed id in the stream; split change refused.
- [ ] AT-W2 order and resume: steps run in stream order; `--max-steps` stops and `--resume`
      continues; a crash injected at each role mid-step, or between the log append and the state
      commit, then a resume, gives byte-identical `map.json` and `log.jsonl` to an uninterrupted
      run; `run` without `--resume` after a commit exits 2; a hand-edited map exits 2; a resume
      with different pinned settings exits 2 and unset flags come from `state.json`.
- [ ] AT-W3 prediction leak: with an updater that copies every canary it sees into the map, a
      canary in item k reaches no predict prompt up to step k and every one after; judge
      exemplars are only earlier items; a context quoting a later item is blanked.
- [ ] AT-W4 sealed slice: a canary in a sealed item appears in no prompt of any role during `run`,
      nor in `map.json`, `map.md`, `log.jsonl`, `curve.json`; a patch citing a sealed or future id
      is rejected.
- [ ] AT-W5 patches: each op applies; each invalid patch kind (malformed ids included) is
      rejected with a reason while the valid ones in the same reply apply; the current item is
      added to evidence; past 24 patches are rejected; consolidation may not add or cite evidence.
- [ ] AT-W6 cap and consolidation: adds past `max_nodes` are rejected and trigger consolidation;
      consolidation reduces the node count; a garbage consolidator still leaves the map under the
      cap by the deterministic prune.
- [ ] AT-W7 threshold: a low-surprise step skips the update; a low-surprise step with a new
      entity or a missed belief updates; an excluded step updates unscored.
- [ ] AT-W8 budget: the guard stops before the cap with exit 4 and the last checkpoint intact; the
      ledger sums to the scripted costs; an unknown cost is charged the estimate; every paid
      attempt is charged; parallel reservations and another process's spend cannot overshoot;
      the final preflight refuses before the seal; a budget stop inside the final leaves the slice
      unused; `cost-estimate` runs N steps and projects the rest.
- [ ] AT-W9 claude JSON: the argv carries `--output-format json`; result, cost and tokens are
      parsed; `is_error` is a failure; anything but the JSON object fails the claude runner; plain
      text from `cmd:` is the reply with an estimated cost.
- [ ] AT-W10 math: surprise per item, rolling window, first and last window, final report fields
      on scripted judges.
- [ ] AT-W11 render: `map.md` is byte-identical across runs and node orderings; `validate` flags
      each schema error.
- [ ] AT-W12 privacy guard: a state dir inside a git work tree exits 3 and writes nothing.
- [ ] AT-W13 end to end: a 40-item synthetic corpus through ingest, split, init, run and final
      with stub runners prints a report (INCONCLUSIVE: 16 sealed items is under `min_n`), and a
      second `final` needs `--rerun-test`.
