"""Helpers for the world-model tests: a split state dir with canaries, a prompt-recording runner.

Invented persona and text only. Unique module name: the repo runs every tests/ dir in one pytest call.
"""

import json

from persona_fixtures import Sandbox, read_jsonl, synth_records, write_jsonl  # noqa: F401
import personalib  # noqa: E402  (path set by persona_fixtures)
import world  # noqa: E402

CANARY_NOW = "zqxcanarynowzqx"
CANARY_LATER = "zqxcanarylaterzqx"
CANARY_SEALED = "zqxcanarysealedzqx"


def split_state(sb, n=40, seed=0, persona="pat", records=None):
    """ingest + split a synthetic corpus; return the state dir."""
    src = sb.root / "samples.jsonl"
    write_jsonl(src, records if records is not None else synth_records(n, seed))
    for script, args in (("ingest.py", ["--persona", persona, src]), ("split.py", ["--persona", persona])):
        r = sb.run(script, *args)
        if r.returncode != 0:
            raise AssertionError(f"{script} failed: {r.stdout}\n{r.stderr}")
    return sb.state(persona)


def plant(d, split_file, index, canary):
    """Append a canary word to one record of a split file; return that record's id."""
    p = d / "split" / split_file
    rows = read_jsonl(p)
    rows[index]["text"] = rows[index]["text"] + " " + canary
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return rows[index]["id"]


class Recorder:
    """Wraps a runner and records every call (role, system, prompt, meta)."""

    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def complete(self, role, model, system, prompt, meta):
        self.calls.append({"role": role, "system": system, "prompt": prompt, "meta": dict(meta),
                           "step": meta.get("step")})
        return self.inner.complete(role, model, system, prompt, meta)


def stub(script=None):
    return personalib.StubRunner(script or {})


def opts(**kw):
    return world.Opts(**kw)


def stream_ids(d):
    return json.loads((d / "stream.json").read_text(encoding="utf-8"))["ids"]
