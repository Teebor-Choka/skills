#!/usr/bin/env python3
"""Check the swe:rust concurrency references (issue #99).

Each `### ` entry in engineering/swe/swe/skills/rust/references/concurrency-*.md needs a
`Symptom:`, `Fix:`, `Source:` (with an https URL) and `Accessed:` (YYYY-MM-DD) line.
SKILL.md must link every such file and name the concurrency triggers in its description.
Each file stays at or below 250 lines (split it past that); the set holds 20 to 30 entries.
"""

import re
import sys
from pathlib import Path

import yaml

SKILL_DIR = Path("engineering/swe/swe/skills/rust")
MAX_LINES = 250
MIN_ENTRIES, MAX_ENTRIES = 20, 30
FIELDS = ("Symptom", "Fix", "Source", "Accessed")
REQUIRED_FILES = ("concurrency-correctness.md", "concurrency-performance.md")
# Entries whose title contains the key must carry a Test: line.
REQUIRE_TEST = ("guard across", "Notify", "loom")
TRIGGERS = (
    "blocking in async",
    "deadlock",
    "cancellation safety",
    "backpressure",
    "atomics ordering",
    "lock contention",
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def entries(text):
    """Yield (title, body) for each `### ` entry, skipping code fences."""
    title, body, fenced = None, [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("### "):
            if title is not None:
                yield title, body
            title, body = line[4:].strip(), []
        elif not fenced and line.startswith("## ") and title is not None:
            yield title, body
            title, body = None, []
        elif title is not None:
            body.append(line)
    if title is not None:
        yield title, body


def check_entry(title, body):
    values = {}
    for ln in body:
        key, _, value = ln.partition(":")
        if key in FIELDS:
            values.setdefault(key, value.strip())
    errors = [f"{title!r}: missing {f}:" for f in FIELDS if f not in values]
    if "Source" in values and not re.search(r"https?://\S+", values["Source"]):
        errors.append(f"{title!r}: Source: has no URL")
    if "Accessed" in values and not DATE_RE.match(values["Accessed"]):
        errors.append(f"{title!r}: Accessed: is not a YYYY-MM-DD date")
    return errors


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    skill = root / SKILL_DIR
    files = sorted((skill / "references").glob("concurrency-*.md"))
    errors = []
    errors += [
        f"missing references/{n}"
        for n in REQUIRED_FILES
        if not (skill / "references" / n).is_file()
    ]
    total = 0
    skill_md = (skill / "SKILL.md").read_text(encoding="utf-8")
    for f in files:
        text = f.read_text(encoding="utf-8")
        if (n_lines := len(text.splitlines())) > MAX_LINES:
            errors.append(f"{f.name}: {n_lines} lines > {MAX_LINES}; split it")
        found = list(entries(text))
        total += len(found)
        if not found:
            errors.append(f"{f.name}: no entries")
        for title, body in found:
            errors += [f"{f.name}: {e}" for e in check_entry(title, body)]
            if any(k in title for k in REQUIRE_TEST) and not any(
                ln.startswith("Test:") for ln in body
            ):
                errors.append(f"{f.name}: {title!r}: missing Test:")
        if f"references/{f.name}" not in skill_md:
            errors.append(f"SKILL.md does not link references/{f.name}")
    if files and not MIN_ENTRIES <= total <= MAX_ENTRIES:
        errors.append(f"{total} entries; expected {MIN_ENTRIES} to {MAX_ENTRIES}")
    head, sep, _ = skill_md.replace("\r\n", "\n").removeprefix("---\n").partition("\n---\n")
    fm = yaml.safe_load(head) if sep else None
    if not isinstance(fm, dict) or not isinstance(fm.get("description"), str):
        errors.append("SKILL.md has no front matter with a description")
    else:
        desc = " ".join(fm["description"].split()).lower()
        errors += [f"description lacks trigger {t!r}" for t in TRIGGERS if t not in desc]
    for e in errors:
        print(f"FAIL {e}")
    print(f"{len(files)} file(s), {total} entr(ies), {len(errors)} error(s).")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
