#!/usr/bin/env python3
"""Fast, dependency-free checks for a portable Agent Skill.

Usage: validate_skill.py <skill-dir> [<skill-dir> ...]

Validates the portable contract shared by Claude Code, Codex, and OpenCode:
- SKILL.md exists, with YAML frontmatter fenced by '---'.
- name: required, ^[a-z0-9][a-z0-9-]*$, <=64 chars, equals the directory name.
- description: required, <=1024 chars, no angle brackets (< or >).
Warnings (do not fail the build) flag portability risks:
- frontmatter keys outside the portable set (name, description, license, compatibility, metadata).
- agent-specific tool calls in the body (Task(, @"... (agent)", skill({) that break cross-agent use.
- a body longer than 500 lines.

Exit code 0 if every skill passes the hard checks (warnings allowed), else 1.
Uses only the standard library, so it runs anywhere Python 3 does.
"""
import os
import re
import sys

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
NONPORTABLE_BODY = [
    (re.compile(r"\bTask\("), 'Task( ... ) call'),
    (re.compile(r'@"[^"]*\(agent\)"'), '@"name (agent)" mention'),
    (re.compile(r"\bskill\(\{"), "skill({ ... }) call"),
]


def split_frontmatter(text):
    """Return (frontmatter_str, body_str) or (None, None) if not fenced by '---'."""
    if not text.startswith("---\n"):
        return None, None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, None
    return text[4:end], text[end + 5 :]


def top_level_keys(fm):
    return [m.group(1) for m in re.finditer(r"(?m)^([A-Za-z0-9_-]+):", fm)]


def get_scalar(fm, key):
    """Extract a top-level scalar, handling inline and folded/literal ('>' or '|') blocks."""
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest and rest[0] in "|>":  # folded/literal block: collect indented continuation
            parts = []
            for cont in lines[i + 1 :]:
                if cont.strip() == "" or cont[:1] in (" ", "\t"):
                    parts.append(cont.strip())
                else:
                    break
            return " ".join(p for p in parts if p)
        return rest.strip().strip('"').strip("'")
    return None


def validate(skill_dir):
    errors, warnings = [], []
    md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(md):
        return [f"no SKILL.md in {skill_dir}"], []
    with open(md, encoding="utf-8") as f:
        text = f.read()

    fm, body = split_frontmatter(text)
    if fm is None:
        return ["frontmatter must be fenced by '---' on its own lines"], []

    keys = top_level_keys(fm)
    for k in keys:
        if k not in PORTABLE_KEYS:
            warnings.append(f"non-portable frontmatter key '{k}' — keep it in an agent adapter, not the core")

    name = get_scalar(fm, "name")
    dirname = os.path.basename(os.path.normpath(skill_dir))
    if not name:
        errors.append("missing required field: name")
    else:
        if len(name) > 64:
            errors.append(f"name too long: {len(name)} > 64")
        if not NAME_RE.match(name):
            errors.append(f"name must match ^[a-z0-9][a-z0-9-]*$: {name!r}")
        if name != dirname:
            errors.append(f"name {name!r} must equal the directory name {dirname!r}")

    desc = get_scalar(fm, "description")
    if not desc:
        errors.append("missing required field: description")
    else:
        if len(desc) > 1024:
            errors.append(f"description too long: {len(desc)} > 1024")
        if "<" in desc or ">" in desc:
            errors.append("description must not contain angle brackets (< or >)")

    for rx, label in NONPORTABLE_BODY:
        if rx.search(body or ""):
            warnings.append(f"body contains an agent-specific {label} — describe the intent instead, bind it in an adapter")

    n = len((body or "").splitlines())
    if n > 500:
        warnings.append(f"SKILL.md body is {n} lines (>500) — move detail into references/")

    return errors, warnings


def main():
    if len(sys.argv) < 2:
        sys.exit(f"usage: {sys.argv[0]} <skill-dir> [<skill-dir> ...]")
    failed = 0
    for d in sys.argv[1:]:
        errors, warnings = validate(d)
        label = os.path.basename(os.path.normpath(d))
        if errors:
            failed += 1
            print(f"FAIL {label}")
            for e in errors:
                print(f"     error: {e}")
        else:
            print(f"OK   {label}")
        for w in warnings:
            print(f"     warn:  {w}")
    print(f"\n{len(sys.argv) - 1} skill(s) checked, {failed} failure(s).")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
