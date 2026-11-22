# persona

Learn how one person communicates and thinks from samples of their material, then draft and answer as that persona.

| Skill            | Use                                                                                                  |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| `persona:build`  | samples to a persona (world model map or voice profile), proven on held-out items with a blind judge |
| `persona:write`  | draft a message as the persona, in a channel and length                                              |
| `persona:advise` | answer a question as the persona's advisor, with a grounding line and a confidence statement         |

Every answer from `write` and `advise` is a simulation built from the material. Neither skill invents quotes or claims to be the real person.

## State and privacy

All data lives in `~/.config/agents/state/persona/<name>/` (override with `PERSONA_STATE_HOME`; `MIMIC_STATE_HOME` still works for one release). Samples, splits, maps, logs and reports are personal data and stay out of every repository: the scripts refuse a path inside a tracked git tree. Move an old state directory with `mv ~/.config/agents/state/voice ~/.config/agents/state/persona`.

## Build by predicting (default)

The world model map is built one item at a time. For each next item the model is asked what the person would produce from the situation alone, a blind judge compares that prediction with the actual item, and only then is the item learned, as small validated patches to the map. The prediction error over the stream is the learning curve. The held-out slice is never ingested and is judged once at the end.

```
S=communication/persona/skills/build/scripts
python3 $S/ingest.py   --persona NAME [--exclude-pattern REGEX] FILES...
python3 $S/split.py    --persona NAME [--seed N]
python3 $S/world.py init          --persona NAME
python3 $S/world.py cost-estimate --persona NAME --runner claude --steps 10
python3 $S/world.py run           --persona NAME --runner claude --max-cost-usd X [--resume]
python3 $S/world.py final         --persona NAME --runner claude --max-cost-usd X
python3 $S/world.py status|render|validate --persona NAME
```

- `cost-estimate` runs a few real steps and projects the cost of the whole stream. Run it first.
- The budget guard logs every call's cost to `ledger.jsonl` and refuses the call that would pass `--max-cost-usd` (exit 4). A failed call is charged at its estimate, so the ledger is an upper bound. `run` checkpoints each step and `--resume` continues exactly.
- `final` needs `--rerun-test REASON` for a second run on the same slice.
- The fold-based profile loop (`profile.py`, `evaluate.py`) remains available for a plain voice profile.

## Limits

- Treat one test slice of a few dozen items as a trend, not a result. The best of several dev rounds is optimistic.
- Short written text can approach the pass band. Spoken text taken from auto-generated captions does not converge: the captions carry cut points and glitches that a clean generator does not reproduce. Use clean transcripts or the person's own writing for a spoken channel.
- For several channels, default to one persona with per-channel sections.
- Check `status` after a long run: steps whose calls failed show no surprise value and were not learned from.
