---
name: advise
description: Answer a question as a persona's advisor, reasoning from its world model map (beliefs, decision rules, reaction patterns, format rules) and ending with a grounding line of the map nodes used and their confidence. Input is the persona name and the question. Use for "ask the persona advisor", "what would the persona advise about X", "advise me as the persona", "how would the persona react to this". Needs a map built by persona:build. Not for drafting a message in the persona's voice (persona:write), not for building or revising a persona (persona:build), and not for plain advice with no persona.
license: MIT
compatibility: Any agent that can read files and run python3 (stdlib only).
---

# advise

Answer one question the way a persona's advisor would, from the map and nothing else. The answer
is a simulation built from the material, not the person.

## Input

- `persona`: the name of a persona built by `build`.
- `question`: what to advise on. Ask for a missing persona or question; do not guess them.

## Load

State dir: `$PERSONA_STATE_HOME/<persona>/`, else `~/.config/agents/state/persona/<persona>/`.

1. Read `map.md` there. Read `map.json` only when you need evidence ids or exact confidence. With
   no valid map, stop and say so; do not advise from the name.
2. Load this one persona only. Never read other personas' directories, `test.jsonl`,
   `items.jsonl`, `corpus.jsonl`, `log.jsonl`, `final/` or any report.
3. Never write to the state dir. The skill is read-only.
4. Multi-turn: the persona stays loaded. A follow-up reuses the same nodes; reload only when the
   user names another persona or says the map changed.

## Answer

1. Find the beliefs, decision rules and reaction patterns that bear on the question. Reason from
   them to a recommendation, and give the rule that drives it.
2. Write in the persona's format rules for the channel and band. Short or long as the question
   asks.
3. Disagree with the user when the map's rules say so. Do not soften it.
4. End with the grounding line, from the node ids you used:
   `python3 scripts/grounding.py --map <state dir>/map.json <id> [<id> ...]`.
   Print its line as is. It exits 2 and names an id the map does not have: fix the ids.
5. Label the answer: "Simulation of an advisor built from the material, not the person."

## When the map is thin

- No evidence on the question: say so ("extrapolating from rules X and Y, low confidence") and
  list what the map would need (kind of samples, topic).
- A question on the persona's current real opinion of a recent event: answer "outside the map",
  then give the closest rule and mark it as such.

## Honesty

- Never invent a quote, fact, event or number about the real person. Never claim to be them.
- Facts the user states are theirs; do not add any.
- For a living private individual, work only from the user's own corpus or public material, with
  the consent rules of `build` (references/privacy.md there).

## Not this skill

Drafting text in the persona's voice: `persona:write`. Building or revising a persona:
`persona:build`.
