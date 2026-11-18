#!/usr/bin/env python3
"""Check the swe:rust concurrency references (issue #99).

Each `### ` entry in engineering/swe/skills/rust/references/concurrency-*.md needs a
`Symptom:`, `Fix:`, `Source:` (with an https URL) and `Accessed:` (YYYY-MM-DD) line.
SKILL.md must link every such file and name the concurrency triggers in its description.
Each file stays at or below 250 lines (split it past that); the set holds 20 to 30 entries.
"""

import re
import sys
from pathlib import Path

import yaml

SKILL_DIR = Path("engineering/swe/skills/rust")
MAX_LINES = 250
MIN_ENTRIES, MAX_ENTRIES = 20, 30
FIELDS = ("Symptom", "Fix", "Source", "Accessed")
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
    errors = []
    for field in FIELDS:
        lines = [ln for ln in body if ln.startswith(f"{field}:")]
        if not lines:
            errors.append(f"{title!r}: missing {field}:")
    src = [ln for ln in body if ln.startswith("Source:")]
    if src and not re.search(r"https?://\S+", src[0]):
        errors.append(f"{title!r}: Source: has no URL")
    acc = [ln for ln in body if ln.startswith("Accessed:")]
    if acc and not DATE_RE.match(acc[0].split(":", 1)[1].strip()):
        errors.append(f"{title!r}: Accessed: is not a YYYY-MM-DD date")
    return errors


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    skill = root / SKILL_DIR
    files = sorted((skill / "references").glob("concurrency-*.md"))
    errors = []
    if not files:
        errors.append("no references/concurrency-*.md files")
    total = 0
    skill_md = (skill / "SKILL.md").read_text(encoding="utf-8")
    for f in files:
        text = f.read_text(encoding="utf-8")
        n_lines = len(text.splitlines())
        if n_lines > MAX_LINES:
            errors.append(f"{f.name}: {n_lines} lines > {MAX_LINES}; split it")
        found = list(entries(text))
        total += len(found)
        if not found:
            errors.append(f"{f.name}: no entries")
        for title, body in found:
            errors += [f"{f.name}: {e}" for e in check_entry(title, body)]
        if f"references/{f.name}" not in skill_md:
            errors.append(f"SKILL.md does not link references/{f.name}")
    if files and not MIN_ENTRIES <= total <= MAX_ENTRIES:
        errors.append(f"{total} entries; expected {MIN_ENTRIES} to {MAX_ENTRIES}")
    fm = yaml.safe_load(skill_md.split("\n---\n", 1)[0].removeprefix("---\n"))
    desc = " ".join(fm["description"].split()).lower()
    errors += [f"description lacks trigger {t!r}" for t in TRIGGERS if t not in desc]
    for e in errors:
        print(f"FAIL {e}")
    print(f"{len(files)} file(s), {total} entr(ies), {len(errors)} error(s).")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
