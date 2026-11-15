#!/usr/bin/env python3
"""Check a prose-to-procedure translation: every sentence is traced to the machine or is a gap.

A translator (an LLM) maps prose onto the procedure format. This check is the code half: it proves
that no sentence was silently dropped and that every claimed element exists. A gap is a sentence
the machine cannot express yet, with the missing capability named: it is how the format grows.

    check_translation.py TRANSLATION PROCEDURE
"""
import argparse
import sys

from validate_procedure import ID_MAPS, parse_frontmatter, parse_procedure

__all__ = ("check_translation", "main")

REF_KINDS = ("stages", *ID_MAPS)


def _ref_error(sid, ref, proc):
    kind, _, key = ref.partition(".") if isinstance(ref, str) else ("", "", "")
    if kind not in REF_KINDS or not key:
        return f"trace {sid}: '{ref}' must look like stages.<id> or <{'|'.join(ID_MAPS)}>.<id>"
    if key not in proc.get(kind, {}):
        return f"trace {sid}: '{ref}' does not exist in the procedure"
    return None


def _named_text(value):
    return isinstance(value, str) and bool(value)


def check_translation(translation_text, procedure_text, src="<translation>"):
    """Return (errors, gaps). A gap is a sentence the machine cannot express yet."""
    proc, errs = parse_procedure(procedure_text, "<procedure>")
    fm, errs2 = parse_frontmatter(translation_text, src)
    if errs or errs2:
        return errs + errs2, []
    sentences, trace, gaps = fm.get("sentences"), fm.get("trace") or {}, fm.get("gaps") or {}
    if not isinstance(sentences, dict) or not sentences:
        return [f"{src}: needs a 'sentences' map with at least one sentence"], []
    errs = [
        f"{src}: '{name}' must be a map of ids"
        for name, value in (("trace", trace), ("gaps", gaps))
        if not isinstance(value, dict)
    ]
    if errs:
        return errs, []
    errs += [f"sentence '{sid}' must be non-empty text" for sid, text in sentences.items() if not _named_text(text)]
    errs += [f"'{sid}' is in trace or gaps but is not a sentence" for sid in (*trace, *gaps) if sid not in sentences]
    for sid in sentences:
        if sid in trace and sid in gaps:
            errs.append(f"sentence '{sid}' is both traced and a gap: pick one")
        elif sid not in trace and sid not in gaps:
            errs.append(f"sentence '{sid}' is silently dropped: trace it or list it as a gap")
    for sid, refs in trace.items():
        if not isinstance(refs, list) or not refs:
            errs.append(f"trace {sid}: must list at least one element of the procedure")
            continue
        errs += [e for ref in refs if (e := _ref_error(sid, ref, proc))]
    open_gaps = []
    for sid, gap in gaps.items():
        needs = gap.get("needs") if isinstance(gap, dict) else None
        if not _named_text(needs):
            errs.append(f"gap {sid}: 'needs' must name the capability the machine lacks")
        elif sid in sentences:
            open_gaps.append({"id": sid, "sentence": sentences[sid], "needs": needs})
    order = {sid: i for i, sid in enumerate(sentences)}
    return errs, sorted(open_gaps, key=lambda g: order[g["id"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("translation")
    ap.add_argument("procedure")
    a = ap.parse_args(argv)
    try:
        texts = [open(p, encoding="utf-8").read() for p in (a.translation, a.procedure)]
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errs, gaps = check_translation(*texts, a.translation)
    for e in errs:
        print(f"ERROR: {e}", file=sys.stderr)
    for g in gaps:
        print(f"GAP {g['id']}: needs {g['needs']} ({g['sentence']})")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
