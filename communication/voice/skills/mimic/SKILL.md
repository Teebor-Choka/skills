---
name: mimic
description: Learn how one person communicates from samples of their messages and write a voice profile that lets a model write as them, chat replies and one-liners included, then prove it on held-out messages with a blind judge. Use for "write like me", "mimic this person", "learn my voice from these samples", "build a voice profile", or drafting a short message or chat reply in a persona's voice. Not for generic de-slop or removing AI tells (writing:unslop), nor for editing your own draft while keeping your voice (prose-craft voice matching).
license: MIT
compatibility: Python 3.13 or newer, standard library only. The live judge needs the claude CLI or any command that reads a prompt on stdin.
---

# mimic

Build a guideline file (the profile) from TRAIN samples, then show on TEST samples it never saw
that a blind judge cannot tell the generated messages from the real ones. The contract, with every
threshold and failure path, is [references/spec.md](references/spec.md).

## Before you start: the data is personal

Tell the user this first, in one or two lines:

- Samples, splits, profile and reports stay in the state dir,
  `~/.config/agents/state/voice/<persona>/` (or `$MIMIC_STATE_HOME/<persona>/`), created 0700.
  They are never committed. The scripts refuse a path that a git work tree would track (exit 3)
  unless `--allow-git-worktree` is passed.
- Mimic a third party only with their consent, or from their public material for study. Never
  send a generated message as if the person wrote it. See [references/privacy.md](references/privacy.md).
- Samples must be the person's own words without AI help, or the profile learns the AI.

## Steps

Scripts live in `scripts/`. Run each with `--persona <name>`.

1. **Ingest.** `ingest.py --persona P [--author A] [--channel C] [--audience A] FILES...` reads
   txt, md, jsonl (`text`, `channel`, `audience`, `ts`, `reply_to`), json, eml and mbox. Text
   stays as written; repeats collapse with a count. Ask for channel and audience when the
   files carry none: the profile depends on them. Drop lines that are not the person's (other
   speakers, bots) with `--exclude-pattern REGEX`; never edit the split files afterwards.
2. **Split.** `split.py --persona P` makes train and test (80/20, at least 20 test items). From
   100 distinct messages it also deals TRAIN into 5 folds for revision. Near duplicates of a
   held-out message never reach train. Once `profile.md` exists, re-splitting needs `--force`.
   Under 50 messages the verdict will be INCONCLUSIVE: say so and ask for more. For a persona
   built from a subset of another's corpus (one channel), `--derive-from OTHER` reuses that split.
   Default to one persona with per-channel sections: on one public figure, a persona per channel
   did not beat it beyond noise (see `references/spec.md`, "Channel strategy"). Written short posts
   get close to the pass band; spoken caption text does not, whatever the profile says.
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
   the selected snapshot. Report the verdict, identification rate, rubric means and the per-band
   and per-channel rows with their verdicts. A second test run needs `--rerun-test "<reason>"`.

Never read `items.jsonl` or a report's worst items to revise the profile: that is training on the
test.

## The judge

Per item: an extractor writes the point of the original without its words; the generator writes
the message from the profile and the point; a blind judge call sees TRAIN exemplars and both
messages in seeded random order and names the original; a second call scores the generated one on
the [rubric](references/rubric.md). Defaults: PASS when the identification rate is within 0.35 to 0.65
and the mean rubric at least 3.5, on at least 20 items. 0.5 means the judge cannot tell; below 0.35
the generated messages overdo the habits (caricature). A judge that
always picks one position, or too many excluded items, makes the round INVALID.

Runners: `--runner claude` (isolated `claude -p`: no tools, no user settings, no session saved),
`--runner cmd:'<command>'` for another harness (prompt on stdin), `--runner stub` for offline
tests. Generator and judge default to the `reasoning` tier, the extractor to `execution`;
`AGENT_TIERS_FILE` maps tiers to models, and `--judge-model` and `--generator-model` take a tier or
a model.

## Drafting as the persona

The selected round's `profile.md` is the input of the `voice-style` skill: load it as the voice for text
written as that person. For a message the user will send themselves, draft it, then check it
against the profile's Short messages and Never sections. Say which profile and round you used and
its last verdict. Without a PASS, call the draft an approximation.

## Tests

`python3 -m pytest tests` (offline, stub runners). The repo's flake `tests` check runs them.
