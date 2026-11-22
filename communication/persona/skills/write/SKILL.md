---
name: write
description: Draft a message as a persona from its validated profile (later also its world model map), in the requested channel and length band. Input is the persona name, the channel, the situation or point, and an optional length target. Use for "write as the persona", "draft this in the persona's voice", "reply as the persona", "answer that chat message the way the persona would". Needs a profile built by persona:build. Not for plain de-slop (writing:unslop), not for editing the user's own draft while keeping their voice (prose-craft), not for answering a question as the persona (persona:advise), and not for building the profile.
license: MIT
compatibility: Any agent that can read files. No scripts.
---

# write

Draft one message as a persona. The profile is the only source of the persona's habits; do not
improvise them from the name.

## Input

- `persona`: the name of a persona built by `build`.
- `channel`: where the message goes (chat, email, post, and so on).
- `point`: the situation or what the message must say.
- `length` (optional): a target in words or a band (short is 25 words or fewer).

Ask for a missing persona, channel or point. Do not guess them.

## Load

State dir: `$PERSONA_STATE_HOME/<persona>/`, else `~/.config/agents/state/persona/<persona>/`
(the old `MIMIC_STATE_HOME` still works for one release).

1. Read `map.md` there (the default build path) and check it with
   `world.py validate --persona <persona>` of the `build` skill. Its format rules per band and
   channel are the profile.
2. If `profile.md` exists (the legacy path), read it too, after
   `profile.py validate --persona <persona>` prints `valid`; on form, its format rules win. With
   neither file valid, stop and say so. Do not draft from a guess.
3. Never read `test.jsonl`, `items.jsonl` or a report. They are evaluation data.

## Draft

1. Pick the band and channel section of the profile that matches the request. A length target
   overrides the band only when the profile allows that length for the channel.
2. Follow that section's rules with its rates: casing, punctuation, emoji, openers, closers,
   signature phrases, and the Never list. Keep to the profile's length range for the band.
3. Reason from the point and the persona's decision rules to what they would say. Do not add
   facts, commitments or names the user did not give.
4. Output only the message, in the channel's form. No preamble, no notes, no options, unless the
   user asked for alternatives.

## Honesty

- Never invent a quote and attribute it to a real person. A draft is new text in their style, not
  something they said.
- Never claim to be the person. If the user asks for something that could pass as the real
  person's own statement (a post under their name, a message sent to a third party), say in one
  line that it is a simulation from a profile and the person has not said it.
- For a living private individual, draft only from the user's own corpus or public material, with
  the consent rules of `build` (references/privacy.md there).
- If the profile has no section for the channel or band, say so, use the closest section, and
  mark the draft as an approximation.
- Without a PASS verdict in the profile's last report, call the draft an approximation.

## Not this skill

Removing AI tells from text: `writing:unslop`. Tightening the user's own draft while keeping their
voice: `writing:prose-craft`. Learning or revising a profile: `persona:build`.
