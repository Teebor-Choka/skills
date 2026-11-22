---
name: build
description: Learn how one person communicates from samples of their messages into a world model map (predicting each message before learning from it) or a voice profile that lets a model write as them, chat replies and one-liners included, then prove it on held-out messages with a blind judge. Use for "write like me", "imitate this person", "learn my voice from these samples", "build a voice profile". Not for drafting a message from a finished profile (persona:write), nor for answering a question as the persona (persona:advise), generic de-slop or removing AI tells (writing:unslop), nor for editing your own draft while keeping your voice (prose-craft voice matching).
license: MIT
compatibility: Python 3.13 or newer, standard library only. The live judge needs the claude CLI or any command that reads a prompt on stdin.
---

# build

Learn a persona from samples, then show on samples it never saw that a blind judge cannot tell
the generated messages from the real ones. The default path builds a world model map by predicting
each message before learning from it ([references/world-model.md](references/world-model.md)). The
legacy path writes a profile by hand and revises it on folds
([references/spec.md](references/spec.md)). Both share ingest, split, the judge and the report.

## Before you start: the data is personal

Tell the user this first:

- Samples, splits, profile and reports stay in the state dir,
  `~/.config/agents/state/persona/<persona>/` (or `$PERSONA_STATE_HOME/<persona>/`), created 0700.
  They are never committed. The scripts refuse a path that a git work tree would track (exit 3)
  unless `--allow-git-worktree` is passed.
- Imitate a third party only with their consent, or from their public material for study. Never
  send a generated message as if the person wrote it. See [references/privacy.md](references/privacy.md).
- Samples must be the person's own words without AI help, or the profile learns the AI.

## Steps

Scripts live in `scripts/`. Run each with `--persona <name>`. Steps 1 and 2 are shared.

1. **Ingest.** `ingest.py --persona P [--author A] [--channel C] [--audience A] FILES...` reads
   txt, md, jsonl (`text`, `channel`, `audience`, `ts`, `reply_to`), json, eml and mbox. Text
   stays as written. Ask for channel and audience when the
   files carry none. Drop lines that are not the person's (other
   speakers, bots) with `--exclude-pattern REGEX`; never edit the split files afterwards.
2. **Split.** `split.py --persona P` makes train and test (80/20, at least 20 test items). From
   100 distinct messages it also deals TRAIN into 5 folds for revision. Near duplicates of a
   held-out message never reach train. Once `profile.md` exists, re-splitting needs `--force`.
   Under 50 messages the verdict will be INCONCLUSIVE: say so and ask for more. For a persona
   built from a subset of another's corpus (one channel), `--derive-from OTHER` reuses that split.
   Default to one persona with per-channel sections (`references/spec.md`, "Channel strategy").

### Default path: the predictive loop

3. **Init.** `world.py init --persona P` orders TRAIN into the stream (by time when every message
   has a parseable timestamp, else a recorded seeded order). The test slice is sealed: never
   streamed, never shown to the loop.
4. **Estimate.** `world.py cost-estimate --persona P --steps 10` runs 10 real steps and projects
   the cost of the rest and of the final. Tell the user the projection and agree a cap.
5. **Run.** `world.py run --persona P --max-cost-usd X`. Per message: the point is extracted
   without its words, the map predicts the message, a judge compares prediction and actual, and
   the map gets small patches when the surprise is high or the message shows something new. It
   checkpoints every step; on exit 4 (cap reached) continue with `--resume` and a higher cap. After
   3 failed attempts at one step it halts (exit 5): fix the cause, `--resume --retry-failed`.
   `world.py status` shows progress, the surprise curve, and measured and estimated cost.
6. **Final.** `world.py final --persona P` judges the sealed slice once with the frozen map. Report
   the verdict, the per-band and per-channel rows, the first and last curve window, and the cost.
   A second run needs `--rerun-test "<reason>"`.

`map.md` in the state dir is what `write` loads. `world.py validate` checks `map.json`.

### Legacy path: a hand-written profile revised on folds

3. **Analyze.** `profile.py analyze --persona P` writes `analysis-stats.md` from TRAIN. Then a
   reasoning-tier agent that reads only TRAIN and those stats writes `analysis.md` in the state
   dir: the person's mental model (beliefs, framing, reasoning moves, emotional range, stance,
   reactions, decisions, and how the same mind shows up compressed in short messages and expanded
   in long form). Paraphrase; never quote.
4. **Skeleton.** `profile.py skeleton --persona P` writes `profile.md` with measured stats,
   worked-example candidates and a `TODO` per section and mental model subsection. Sections are
   in [references/profile-schema.md](references/profile-schema.md).
5. **Write the profile from TRAIN and `analysis.md` only.** Never open `test.jsonl`. Write the
   mental model first, then derive the rules per format (Short messages, Long messages) from it,
   with rates, not adjectives. Keep 3 to 6 worked examples. Most persona failures are one-liners:
   follow [references/short-messages.md](references/short-messages.md).
6. **Validate.** `profile.py validate --persona P` until it prints `valid`.
7. **Revise on folds (only with folds).** `evaluate.py run --persona P --slice dev` judges round k
   on TRAIN fold `(k - 1) mod 5`. The writer of each revision sees only TRAIN without that fold
   (`profile.py validate --fold F` checks it), `analysis.md` and the round's `feedback.json`.
   Read the per-band rows first: format closeness (short and long) is the goal. Repeat until the
   round prints a stop: converged, plateau or 10 rounds.
8. **Select.** `evaluate.py select --persona P` records the round whose profile the test uses
   (worst band closest to 0.5 at rubric 3.5 or more, ties within noise to the latest). Do it
   before the test, and say which round it picked and why.
9. **Test once.** `evaluate.py run --persona P --slice test`. This seals the test slice and runs
   the selected snapshot. Report the verdict and the band and channel rows. A second run needs `--rerun-test "<reason>"`.

Never read `items.jsonl` or a report's worst items to revise the profile: that is training on the
test.

## The judge

Per item: an extractor writes the point of the original without its words; the generator writes
the message from the profile and the point; a blind judge call sees TRAIN exemplars and both
messages in seeded random order and names the original; a second call scores the generated one on
the [rubric](references/rubric.md). Defaults: PASS when the identification rate is within 0.35 to 0.65
and the mean rubric at least 3.5, on at least 20 items. Below 0.35 the generated messages overdo the habits (caricature). A judge that
always picks one position, or too many excluded items, makes the round INVALID.

Runners: `--runner claude`, `cmd:'<command>'` (another harness, prompt on stdin) or `stub` (offline
tests). Generator and judge default to the `reasoning` tier, the extractor to `execution`; model
flags and `AGENT_TIERS_FILE` are in [references/world-model.md](references/world-model.md).

Every call's cost lands in `<state>/ledger.jsonl`. `--max-cost-usd X` refuses the call that would
pass `X` (exit 4); sealed runs check the estimate before sealing.

## Drafting as the persona

`map.md` (default path) or the selected round's `profile.md` (legacy path) is the input of the
`write` skill (the voice for text written as that person). For a message the user sends
themselves, draft it, then check it against the profile's Short messages and Never sections. Say
which map or profile you used and its last verdict; without a PASS, call the draft an approximation.

## Tests

`python3 -m pytest tests` (offline, stub runners); the flake `tests` check runs them.
