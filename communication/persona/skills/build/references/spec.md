# build: specification

Intent: from samples of how one person writes, build a guideline file (the profile) that lets a
model write as that person, including chat replies and one-liners, and prove it with a held-out
test judged blind by a separate, stronger model invocation.

The skill is persona-agnostic and public. Every sample, split, profile and report is personal data
and lives only in the state dir (see [privacy.md](privacy.md)).

## Pipeline

```
samples ─ ingest.py ─▶ corpus.jsonl ─ split.py ─▶ train (5 folds) / test
train ─ profile.py analyze ─▶ analysis-stats.md ─ analysis agent ─▶ analysis.md (mental model)
train ─ profile.py skeleton ─▶ profile.md (stats + mental model + rules + TODO)
agent fills profile.md from TRAIN and analysis.md ─ profile.py validate
evaluate.py run --slice dev  ─▶ feedback.json on a rotating fold ─▶ agent revises (until the stop rule)
evaluate.py select           ─▶ rounds/selection.json (the profile the test will use)
evaluate.py run --slice test ─▶ report (once, sealed, on the selected profile)
profile.md ─▶ write (drafting as the persona)
```

All scripts are Python 3 stdlib only, deterministic for a given input and seed, and run offline
except the `claude` runner.

## Valid inputs

- Persona name: `^[a-z0-9][a-z0-9_-]{0,63}$`. Anything else exits 2.
- State dir: `--state-dir DIR`, else `$MIMIC_STATE_HOME/<persona>/`, else
  `~/.config/agents/state/persona/<persona>/` (agent usage data lives under `~/.config/agents/`).
  Created with mode 0700; files written 0600.
- Guard, before anything is written: when the target sits inside a git work tree (a `.git` dir
  or file in an ancestor), `git check-ignore -q <target>` must succeed, so git would never track
  it. `~/.config/agents` is such a tree, and its allowlist `.gitignore` ignores `/state/`. An
  unignored target, or a `.git` that git cannot resolve, exits 3. The target is resolved through
  symlinks first, so a link into a repo is caught. An existing state dir is tightened to 0700.
  `--allow-git-worktree` overrides.
- Sample files, by extension:
  - `.txt`, `.md`: messages separated by a line that is exactly `---`; with no such line, by blank
    lines. A leading YAML front matter block in `.md` is skipped.
  - `.jsonl`, `.ndjson`: one JSON object per line. `text` is required; `channel`, `audience`, `ts`,
    `reply_to`, `context`, `author`, `id` are optional. `reply_to` that equals another record's
    `id` in the same file resolves to that record's text; otherwise it is taken as literal context.
    With `--author NAME`, records whose `author` differs are dropped (they still resolve
    `reply_to`). A bad line exits 2 naming the file and line.
  - `.json`: an array of the same objects.
  - `.eml` (one message), `.mbox` (many): the `text/plain` body; quoted lines (`>`), the
    `On ... wrote:` line and everything after `-- ` (signature) are removed. Subject becomes
    context, channel is `email`. With `--author`, only messages whose `From` contains it.
  - Any other extension exits 2.
- `--channel` and `--audience` set the default for records that have none (default `default`).
- `--exclude-pattern REGEX` (repeatable) drops matching messages, for example other speakers'
  lines in a transcript. A bad regex exits 2. Filtering happens only here: to filter a corpus,
  re-ingest and re-split. Editing split files in place is not supported (leak risk).

## Expected outputs

### ingest.py

`corpus.jsonl`, one record per kept message: `id` (sha256 of the stored text, 12 hex), `text`
(stored as written: casing, punctuation, emoji, dashes and line breaks kept; only surrounding
whitespace and trailing spaces per line are trimmed), `channel`, `audience`, `ts`, `context`,
`source`, `words`, `band`, `count`.

- Empty or whitespace-only messages are dropped.
- Exact duplicates (same text after whitespace collapse) collapse into one record with `count`
  incremented. Frequency is a habit signal and is kept.
- `band` is `short` for 25 words or fewer (a chat reply, a one-liner, an emoji), else `long`.
- Prints one summary line: kept, dropped empty, excluded, duplicates, short, long.

### split.py

`split/train.jsonl`, `split/dev.jsonl` (empty: folds replaced the dev slice), `split/test.jsonl`,
`split/manifest.json`.

- Near-duplicate clusters first: two messages are near duplicates when their canonical forms
  (NFKC, lowercase, punctuation and symbols removed, whitespace collapsed; for an emoji- or
  punctuation-only message, its NFKC text) are equal or their character 4-gram Jaccard is at
  least `--near-dup` (default 0.7). Clusters are unions of such pairs.
- The unit of assignment is the cluster. A cluster sent to test or dev contributes only its first
  member (corpus order); its other members are dropped, never put in train. This is the leak guard.
- Sizes, with N clusters: test `T = max(round(N * test_frac), min(min_test, floor(N * 0.4)))`
  (defaults 0.2 and 20). So 50 messages already reach the 20 test items a verdict needs, and below
  50 the verdict is INCONCLUSIVE by construction (see Thresholds). From 2 clusters, T is at least 1.
- Folds: when `N >= 100` (`--dev-min`), TRAIN clusters are dealt into `--folds` folds (default 5)
  and each train record carries `fold`. Per `(band, channel, audience)` stratum, clusters are
  shuffled with the same rng and dealt round robin starting at the fold with the fewest records,
  so every fold holds a near-equal share of each stratum and a cluster never spans two folds.
  `--folds 0` turns them off.
- `--derive-from PERSONA` (for a persona whose corpus is a subset of another's, such as one
  channel): train, test and folds are the source persona's, restricted to the messages this
  corpus holds; no new draw. The leak check below runs again, and the manifest records
  `derived_from` (persona and source split id). Messages absent from the source split are dropped.
- Stratified by `(band, channel, audience)`: each stratum gets its share of T by largest
  remainder. If a band with at least 2 clusters ends up with no test item, one slot moves to it
  from the largest stratum. Short messages are always represented when the corpus has them.
- Seeded (`--seed`, default 1337): clusters are sorted by id, then shuffled with
  `random.Random(seed)`. Same corpus and seed give byte-identical files.
- After the split, every held-out item is checked against every train item; any pair at or above
  the threshold aborts with exit 2. A train record whose `context` (a `reply_to` chain) nearly
  repeats a held-out message, or contains one of 3+ tokens, gets its context blanked, because the
  profile author reads train. The manifest records the counts, strata, seed, the highest cross
  similarity, the redacted contexts, the corpus hash and the split id (a hash of the held-out ids).
- Re-splitting exits 2 unless `--force` when the test slice is sealed or a `profile.md` exists:
  its author has read the current train, which a new split would move into the test.

### profile.py

- `skeleton` writes `profile.md` from TRAIN only: the fixed sections of
  [profile-schema.md](profile-schema.md), a `Measured stats` section computed from train (length
  distribution per band and channel, casing, punctuation and emoji rates, top openers and closers,
  repeated phrases) and worked-example candidates (up to two per band and channel), with `TODO`
  in each section the agent must write. It refuses to overwrite an existing profile without
  `--force`.
- `analyze` writes `analysis-stats.md` from TRAIN: the measured stats for all channels and per
  channel, including hedging, questions, imperative openers, person and tense per 100 words,
  sentence rhythm and top words. A reasoning-tier analysis agent reads it with TRAIN (nothing
  else) and writes `analysis.md`, the person's mental model, before the profile is written.
- `validate` exits 0 when the profile is complete and clean, 1 with one line per error:
  a `split:` line that is not the current split id, missing or empty section, a missing or empty
  `Mental model` subsection, a leftover `TODO`, fewer than 3 or more than 6 worked examples, no
  short worked
  example while train has short messages, a worked example whose id is not in TRAIN or whose
  text differs from it, a channel with 3 or more train messages not named in the channel matrix,
  a profile over 16 KB, or a held-out leak: a 6-token span of any dev or test message (or the
  whole message when it has 3 to 5 tokens) that appears in the profile and in no train message.
  `--fold F` validates for the round on fold F: that fold's records count as held out, except the
  profile's own worked examples, which are never judged.

### evaluate.py run

For each item of the chosen slice (`--slice dev`: the round's fold of TRAIN, minus the profile's
worked examples; `--slice test`: the test slice). On a dev round the rest of TRAIN is the
exemplar pool and the fold is held out everywhere (validation, exemplars, feedback sanitizing):

1. **Extract** (execution tier): the point, the context and the intent of the original, as JSON,
   without its wording. Point, context and intent together are checked: sharing a run of 4 or
   more canonical tokens with the original, or containing the whole of an original shorter than
   4 tokens (an emoji-only original by its characters), is a leak: retry once
   with a stricter instruction, then exclude the item (`point_leak`).
2. **Generate** (reasoning tier): the message, from the profile, the channel, the audience, the
   context and the point only. A generated text of an 8+ token original that is near-identical to
   it (Jaccard at least 0.9) is excluded (`copied`).
3. **Identify** (judge, reasoning tier, blind): up to 4 TRAIN exemplars of the same channel and
   band, the context and point, and the two candidates as A and B in an order drawn from
   `random.Random(f"{seed}:{round}:{item_id}")`. The judge names the original.
4. **Score** (judge, a second invocation, unblinded): the original as reference, the generated
   message, and the rubric of [rubric.md](rubric.md): voice, length, register, habit,
   temperament, 0 to 5 with a one-line reason each.

Identification is blind and scoring is a separate call, so knowing which one is generated
cannot bias the pick. A judge reply that does not parse counts against the persona: as a correct
identification, and as 0 on every dimension.

Outputs in `rounds/<slice>-<k>/`: `items.jsonl` (everything, with text), `report.json`,
`report.md` (printed to stdout). A dev round also writes `profile.md` (the exact profile it
judged), records `fold`, `revised` (profile hash differs from the previous round) and the stop
rule's result, and writes `feedback.json`, which holds aggregates
only: dimension means, failed dimensions, breakdowns, and judge reasons with quoted spans removed
and dropped entirely when they share a 4-token span with any held-out message (or the whole of a
2 or 3 token one). A shorter fragment, or a one-word message, can still appear in a reason; that
is accepted, since a single word carries no message. A test round writes no feedback.

## Thresholds and verdict

Defaults: `--max-id-rate 0.65`, `--min-rubric 3.5`, `--min-n 20`, `--dim-floor 3.0`.

- identification rate = correct picks / scored items. 0.5 means the judge cannot tell.
- With 20 items and a judge that cannot tell, P(14 or more correct) = 0.058. A rate of 0.65 or
  less (13 of 20 or fewer) is therefore what chance produces at about the 5% level. More items
  tighten it; the default stays fixed and configurable.
- 3.5 on a 0 to 5 scale means most dimensions read "close, with minor slips" (see the rubric).
- Order of the verdict: INVALID when more than 20% of items were excluded (leaks, copies,
  generator errors) or, with at least `min_n` scored items, the judge picked position A in more
  than 80% or fewer than 20% of answers (a degenerate judge scores 50% under random order);
  INCONCLUSIVE when fewer than `min_n` items were scored; PASS when the rate is within
  0.35 to 0.65 and the mean rubric at or above the minimum; FAIL otherwise.
- The band is two-sided. Below 0.35 (7 of 20 or fewer, P = 0.058 by chance, the mirror of the
  upper bound) the judge reliably picks the generated message as the person's: it can tell them
  apart, and the profile exaggerates habits. That is FAIL with a caricature warning.
- Each length band and each channel row carries its own verdict, by the same rules over that
  group's items (its exclusions included). The overall verdict is unchanged by them. With the
  defaults a group under 20 scored items is INCONCLUSIVE.
- Failed dimensions (mean below `--dim-floor`) drive the next revision.
- The report also gives the short exact-match rate: short items whose generated text equals the
  original after normalization. It is a signal (an acknowledgement can match honestly), never
  part of the verdict.

## Revision loop and the sealed test

- Revision reads TRAIN without the round's fold, `analysis.md` and `feedback.json` only. It never
  reads `items.jsonl`, the report or any held-out text.
- Dev round k judges fold `(k - 1) mod 5`, so no item set is reused in consecutive rounds and
  every fold is reused only every fifth round. Caveat: the analysis and earlier profiles were
  written from all of TRAIN, so a fold is not unseen in the abstract; its text cannot enter the
  profile (the validator), and the sealed test stays the only unbiased number.
- Stop rule, checked after each dev round, in this order (`personalib.stop_rule`); `se(n)` is
  `sqrt(0.25 / n)`, the binomial standard error at p 0.5:
  - converged: in the last two rounds every length band has an identification rate in 0.35 to
    0.65 and a rubric of at least 3.5, and no band moved by more than `se` of its smaller n.
  - plateau: from round 4, the worst band (the band farthest from 0.5) of each of the last three
    rounds is no closer to 0.5 than the best earlier round's, less that band's `se`.
  - cap: 10 rounds. A dev round after any stop exits 2.
- Selection (`evaluate.py select`, `personalib.select_round`), written to `rounds/selection.json`
  before the test can run: among rounds whose every band has a rubric of at least 3.5, take the
  round whose worst band is closest to 0.5; rounds within one `se` of it (n of the worst band of
  that best round) tie, and the latest of them wins (it answers the most feedback; profile size
  is recorded, not used). With no round at the floor, the highest worst-band rubric wins, latest
  on a tie, and `floor_met` is false. The record holds the rule text, margin, tie set, fold and
  profile hash. After the seal a new selection exits 2.
- Once any dev round ran, the test needs `rounds/selection.json` and runs on that round's
  `profile.md` snapshot (its hash must still match), not on the current `profile.md`.
- The test slice runs once. The first test run writes `split/test.sealed` with the profile hash,
  after the runner is built and preflighted (a typo or a missing CLI does not burn the seal);
  a second exits 2 unless `--rerun-test REASON`, and that report shows the run count (seal
  entries) and reason.
- Without folds (under 100 clusters) there is no revision loop: build the profile once, then run
  the test. Tiny corpora (under 50) still run, but the verdict is INCONCLUSIVE.

## Channel strategy

For a person who writes in several channels (short posts, spoken transcripts), default to one persona
with per-channel sections in the profile. A separate persona per channel was tried and did not beat it
beyond the noise of a 25 to 35 item test slice, and one persona is simpler.

- Short written text can approach the pass band. Hard length caps, one claim per message and a cap on
  marked quirks per message are what move the rate.
- Spoken text taken from auto-generated captions does not converge: captions carry cut points and
  glitches that a clean generator does not reproduce, and the judge uses them as a tell. Use clean
  transcripts or the person's own writing for a spoken channel, or treat that channel as out of reach.
- Treat one test slice as a trend. The best of several dev rounds is optimistic, so expect the sealed
  test to land worse than the dev rounds.
- Check the stop signal before dispatching another revision round: a round after a plateau stop is
  refused.

## Runners and tiers

- A runner turns `(role, model, prompt)` into text. `--runner claude` runs
  `claude -p --model M --no-session-persistence --tools "" --strict-mcp-config --setting-sources ""
--system-prompt S` with the prompt on stdin, so the user's own instructions, output style and
  hooks cannot pull the persona toward a house voice, and nothing is written to session history.
  Timeout 300 s, one retry. `--runner cmd:'<command>'` runs any command the same way (prompt on
  stdin, `PERSONA_ROLE` and `PERSONA_MODEL` in the environment) for other harnesses. `--runner stub`
  is the in-process test double.
- Tiers: extract uses `execution`; generate and judge use `reasoning`, the strongest. Owner
  decision: no cost cap and no budget flags; the judge and the generator get the strongest model.
  A tier resolves to a model through `AGENT_TIERS_FILE` (the tier map format, harness from
  `AGENT_HARNESS`, default `claude`), else `light`=haiku, `execution`=sonnet, `reasoning`=opus.
  `--extract-model`, `--generator-model` and `--judge-model` take a tier or a model. A judge below
  the reasoning tier (or of unknown tier) runs, and the report carries a warning and the model.
- The stub generator writes a template marked `[stub]`; the stub judge picks by a mode (`coin`
  from the item id, `marker`, `A`, `B`, `garbage`) with per-item overrides from `--stub-script`.

## Failure

| Condition                                             | Behaviour                      |
| ----------------------------------------------------- | ------------------------------ |
| state dir tracked by a git work tree (not ignored)    | exit 3, nothing written        |
| bad persona, unknown extension, bad JSON line         | exit 2 with file and line      |
| no corpus / no split / no profile for the next step   | exit 2 naming the missing step |
| leak found after split                                | exit 2                         |
| `--slice dev` with no folds; a round after a stop     | exit 2                         |
| test after dev rounds with no `selection.json`        | exit 2, test not sealed        |
| selected snapshot edited after selection              | exit 2, test not sealed        |
| `select` with no dev rounds, or after the seal        | exit 2                         |
| second test run without `--rerun-test`                | exit 2                         |
| profile invalid before a run                          | exit 2 with the validator text |
| runner times out or fails twice (extract or generate) | item excluded as `error`       |
| judge fails or returns unparseable output             | counted against the persona    |

## Scale

Built for tens to a few thousand messages. Near-duplicate search is quadratic with a length-ratio
cutoff; 5,000 messages take seconds. An eval round costs 4 model calls per item.

## Dependencies

- Python 3.13 or newer, standard library only. No PyYAML: the repo tooling has it, a user's Python may not.
- `claude` CLI only for `--runner claude`. Its absence exits 2 at the first call.

## Assumptions

- A1: the samples are the person's own words, written without AI help. The skill tells the user
  to remove AI-assisted text, because the profile would learn it.
- A2: 25 words separates short from long well enough for chat versus prose. The stats section
  still shows the full length distribution.
- A3: a judge that sees TRAIN exemplars measures persona match, not human versus model.

## Out of scope

- Impersonating someone without their consent, or to deceive a reader about who wrote a
  message (see [privacy.md](privacy.md)).
- Editing the user's own draft while keeping their voice: that is prose-craft's voice matching.
- Removing AI tells from generic text: that is `writing:unslop`.
- Fine-tuning or storing anything outside the state dir.

## AI-gap closed

"An agent built this, every test passed, and it still behaved wrong":

- The extracted point quotes the original, the generator copies it, the judge flips a coin: a
  fake 50%. Closed by the point-leak and copy checks.
- A judge that always answers A scores 50% under random order: closed by the position-rate check.
- Revision reads the judge's reasons, which quote held-out text: closed by the sanitized,
  aggregates-only feedback and the sealed test.
- A near duplicate of a test message sits in train: closed by cluster assignment and the post-split
  check.
- A tiny corpus reports PASS on 6 items: closed by INCONCLUSIVE below `min_n`.

## Acceptance tests

Offline, with the stub runner, in `tests/test_persona_*.py`:

- [ ] AT-1 guard: an unignored path inside a git work tree exits 3 and writes nothing; an
      ignored path inside one (the dotagents allowlist) and a path outside any work tree are
      allowed; an unresolvable `.git` file is refused; `--allow-git-worktree` lets it through;
      the default dir is `~/.config/agents/state/persona/<persona>`, `MIMIC_STATE_HOME` overrides
      it, the dir is created 0700 and files 0600.
- [ ] AT-2 ingest: txt with `---` and with blank lines, md front matter, jsonl with
      `reply_to` by id and by text, `--author` filter, eml and mbox with quotes and signature
      stripped, empty dropped, duplicates counted, casing, emoji and dashes preserved, band marked,
      bad JSON line and unknown extension exit 2.
- [ ] AT-3 split no-leak: planted near duplicates (case, punctuation, a word changed) of
      held-out items never appear in train; the post-split check finds nothing above threshold.
- [ ] AT-4 split stratification: each `(band, channel)` stratum's test share is within one item
      of proportional; a corpus with few short messages still gets a short test item.
- [ ] AT-5 split sizes: 60 messages give 20 test and no folds; 200 give folds; same seed gives
      identical files, another seed different ones; a sealed split refuses to re-split.
- [ ] AT-6 profile validator: each failure path above yields its error; the filled skeleton
      passes; the skeleton itself fails on `TODO`.
- [ ] AT-7 judge order: positions come from the seed, are reproducible, and are near balanced;
      an always-A judge gives INVALID.
- [ ] AT-8 report math: identification rate, means, per-band and per-channel breakdowns, worst
      items and unparseable verdicts counted against the persona, on scripted verdicts.
- [ ] AT-9 verdict: PASS, FAIL, INCONCLUSIVE and INVALID at and around each threshold; the
      caricature FAIL below the lower bound.
- [ ] AT-10 isolation: no held-out message text reaches `feedback.json`, even when a judge reason
      quotes it; a test round writes no feedback; a 4th dev round and a second test run exit 2.
- [ ] AT-11 leak checks: a point quoting the original is retried then excluded; a copied
      generation is excluded.
- [ ] AT-12 runners: the `claude` argv is the isolated one above; tier resolution honours
      `AGENT_TIERS_FILE`; generator and judge default to the reasoning tier; a weaker judge is
      recorded with a warning.
- [ ] AT-14 folds: 200 messages give 5 folds near equal per band; near duplicates share a fold;
      under 100 clusters no folds; `--derive-from` keeps the source's test and folds for the
      shared messages and records the source split id.
- [ ] AT-15 rounds: dev rounds rotate folds, never judge or show as exemplars a fold item, never
      judge a worked example, snapshot the profile and record `revised`; a profile quoting its
      round's fold is refused; a converged loop refuses another round.
- [ ] AT-16 stop rule and selection on scripted rounds: converged, band moving beyond `se`,
      rubric floor, plateau and cap; selection by worst band, per-band floor, noise tie to the
      latest, exact tie, no round at the floor, no rounds.
- [ ] AT-17 sealed test: refused without a selection or with an edited snapshot, before the seal;
      runs on the selected snapshot when `profile.md` changed later.
- [ ] AT-18 group verdicts: per-band and per-channel verdicts, a group INVALID on its own
      exclusions, the overall verdict unchanged; the report table shows them.
- [ ] AT-19 mental model: the skeleton has every subsection; missing or empty ones and more than
      6 worked examples are errors; the stats carry the analysis measures.
- [ ] AT-13 end to end: 60 synthetic messages through ingest, split, skeleton, fill, validate and
      a test run with stub runners produce a report and a verdict.
