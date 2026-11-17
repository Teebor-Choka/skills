#!/usr/bin/env python3
"""Check a prose-to-procedure translation: every sentence is traced to the machine or is a gap.

A translator (an LLM) maps prose onto the procedure format. This check is the code half. It proves
that no sentence was silently dropped, softened or invented (against the owner's source prose), that
every claimed element exists, and that every gap names the capability the machine lacks. A gap is
how the format grows. It proves coverage, not fidelity: see SKILL.md.

    check_translation.py TRANSLATION PROCEDURE [--source PROSE] [--fail-on-gap]
"""
import argparse
import sys
from collections import Counter

from policy_loader import _strip_inline_comment
from validate_procedure import ID_MAPS, parse_frontmatter, parse_procedure, validate_text

__all__ = ("check_translation", "main")

SECTIONS = ("sentences", "trace", "gaps")
REF_KINDS = ("stages", *ID_MAPS)
MIN_NEEDS_WORDS = 3  # "n/a" and "todo" are not a capability


def _normalize(text):
    return " ".join(text.split())


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _ref_error(sid, ref, proc):
    kind, _, key = ref.partition(".") if isinstance(ref, str) else ("", "", "")
    if kind not in REF_KINDS or not key:
        return f"trace {sid}: '{ref}' must look like stages.<id> or <{'|'.join(ID_MAPS)}>.<id>"
    found = proc.get(kind, {}).get(key)
    if found is None or (isinstance(found, dict) and found.get("disabled") is True):
        return f"trace {sid}: '{ref}' does not exist in the procedure"
    return None


def _raw_errors(text, src):
    """Errors only the raw text shows. The parser keeps the last of a repeated key, cuts a value at
    an unquoted ` #`, files a dedented line under the root, and stops at any `---` line. Each would
    silently shorten what the translator wrote."""
    lines = [line.rstrip("\r") for line in text.split("\n")]
    if sum(1 for line in lines if line.strip() == "---") != 2:
        return [f"{src}: a '---' line other than the opening and closing fence would end the file early"]
    start = next(i for i, line in enumerate(lines) if line.strip())  # the parser skips blank lines and strips the fence
    stop = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "---")
    body = lines[start + 1 : stop]
    errs, sections, section, base, seen = [], set(), None, None, set()
    for line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = stripped.partition(":")
        key = key.strip().strip("\"'")
        if indent == 0:
            if key not in SECTIONS:
                errs.append(f"{src}: unknown top-level key '{key}' (allowed: {', '.join(SECTIONS)})")
            elif key in sections:
                errs.append(f"{src}: section '{key}' appears twice: the parser keeps only the last")
            sections.add(key)
            section, base, seen = key, None, set()
            continue
        base = indent if base is None else base
        if indent != base:
            continue
        if key in seen:
            errs.append(f"{src}: '{key}' appears twice under {section}: the parser keeps only the last")
        seen.add(key)
        value = value.strip()
        if section == "sentences" and _strip_inline_comment(value).strip() != value:
            errs.append(f"sentence '{key}': a '#' starts a comment and would cut the text; quote the sentence")
    return errs


def _source_errors(sentences, prose):
    """Every sentence the owner wrote is in the translation, and the translator added none."""
    owned = Counter(_normalize(line) for line in prose.splitlines() if line.strip())
    kept = Counter(_normalize(t) for t in sentences.values() if _text(t))
    errs = [f"source sentence missing from the translation: '{t}'" for t in (owned - kept)]
    for sid, text in sentences.items():
        if _text(text) and _normalize(text) not in owned:
            errs.append(f"sentence '{sid}' is not in the source: '{text}'")
    return errs


def check_translation(translation_text, procedure_text, src="<translation>", prose=None):
    """Return (errors, gaps). A gap is a sentence the machine cannot express yet.

    With `prose`, the owner's source (one sentence per non-blank line), the translation must
    carry exactly those sentences."""
    bad = [f"procedure is invalid: {e}" for e in validate_text(procedure_text, "<procedure>")]
    fm, errs = parse_frontmatter(translation_text, src)
    if bad or errs:
        return bad + errs, []
    proc, _ = parse_procedure(procedure_text, "<procedure>")
    errs = _raw_errors(translation_text, src)
    sentences, trace, gaps = fm.get("sentences"), fm.get("trace") or {}, fm.get("gaps") or {}
    if not isinstance(sentences, dict) or not sentences:
        return errs + [f"{src}: needs a 'sentences' map with at least one sentence"], []
    shape = [
        f"{src}: '{name}' must be a map of ids"
        for name, value in (("trace", trace), ("gaps", gaps))
        if not isinstance(value, dict)
    ]
    if shape:
        return errs + shape, []
    errs += [f"sentence '{sid}' must be non-empty text" for sid, text in sentences.items() if not _text(text)]
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
        if not _text(needs) or len(needs.split()) < MIN_NEEDS_WORDS:
            errs.append(f"gap {sid}: 'needs' must name the missing capability in at least {MIN_NEEDS_WORDS} words")
        elif sid in sentences:
            open_gaps.append({"id": sid, "sentence": sentences[sid], "needs": needs})
    if prose is not None:
        errs += _source_errors(sentences, prose)
    order = {sid: i for i, sid in enumerate(sentences)}
    return errs, sorted(open_gaps, key=lambda g: order[g["id"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("translation")
    ap.add_argument("procedure")
    ap.add_argument("--source", help="the owner's prose, one sentence per non-blank line")
    ap.add_argument("--fail-on-gap", action="store_true", help="exit 1 while any gap remains")
    a = ap.parse_args(argv)
    try:
        texts = [open(p, encoding="utf-8").read() for p in (a.translation, a.procedure)]
        prose = open(a.source, encoding="utf-8").read() if a.source else None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if prose is None:
        print("WARNING: no --source given; a sentence dropped before translation cannot be detected", file=sys.stderr)
    errs, gaps = check_translation(*texts, src=a.translation, prose=prose)
    for e in errs:
        print(f"ERROR: {e}", file=sys.stderr)
    for g in gaps:
        print(f"GAP {g['id']}: needs {g['needs']} ({g['sentence']})")
    return 1 if errs or (gaps and a.fail_on_gap) else 0


if __name__ == "__main__":
    sys.exit(main())
