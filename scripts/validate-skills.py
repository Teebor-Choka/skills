#!/usr/bin/env python3
"""Validate SKILL.md files against the Anthropic Agent Skills spec.

Rules (from quick_validate.py reference implementation):
- SKILL.md must exist in the skill directory.
- Frontmatter must be valid YAML between --- fences.
- Allowed frontmatter keys: name, description, license, allowed-tools, metadata, compatibility,
  disable-model-invocation.
- name: required, string, ^[a-z0-9][a-z0-9-]*$, no trailing hyphen, no --, max 64 chars.
- description: required, string, no angle brackets, max 1024 chars.
- compatibility (optional): string, max 500 chars.
- SKILL.md size: warn above 8 KB, fail above 16 KB unless listed in scripts/skill-size-allow.txt
  (`<skill path> | <reason> | <split by>`). Only SKILL.md counts; references/ is free.
Usage: validate-skills.py [root] [--size-allow FILE]
"""

import os
import re
import sys

import yaml

ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility",
                "disable-model-invocation"}
MAX_NAME_LEN = 64
MAX_DESC_LEN = 1024
MAX_COMPAT_LEN = 500
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# SKILL.md body size (bytes of that file only; references/ is free).
SIZE_WARN_BYTES = 8 * 1024
SIZE_FAIL_BYTES = 16 * 1024
DEFAULT_SIZE_ALLOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skill-size-allow.txt")


def load_size_allow(path):
    """Parse `<skill path> | <reason> | <split by>` lines. Return (allowed paths, errors)."""
    allowed, errors = set(), []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        return allowed, [f"Cannot read size allowlist {path}: {exc}"]
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3 or not all(parts):
            errors.append(f"{path}:{n}: expected '<skill path> | <reason> | <split by>'")
            continue
        allowed.add(parts[0])
    return allowed, errors


def size_findings(skill_dir, rel, allowed):
    """Return (warnings, errors) for the SKILL.md size of one skill."""
    size = os.path.getsize(os.path.join(skill_dir, "SKILL.md"))
    if size > SIZE_FAIL_BYTES:
        if rel in allowed:
            return [f"SKILL.md is {size} bytes (> {SIZE_FAIL_BYTES}), allowlisted; split it"], []
        return [], [f"SKILL.md is {size} bytes (> {SIZE_FAIL_BYTES}): move detail to references/ "
                    f"or add a reasoned entry to scripts/skill-size-allow.txt"]
    if size > SIZE_WARN_BYTES:
        return [f"SKILL.md is {size} bytes (> {SIZE_WARN_BYTES}): move detail to references/"], []
    return [], []


def find_skills(root):
    """Yield skill directories (dirs containing SKILL.md), excluding node_modules/.git."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", ".claude")]
        if "SKILL.md" in filenames:
            yield dirpath


def validate_skill(skill_dir):
    """Return a list of error strings for the skill, or [] if valid."""
    errors = []
    skill_md = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(skill_md, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        return [f"Cannot read SKILL.md: {exc}"]

    if not content.startswith("---\n"):
        return ["SKILL.md frontmatter must start with '---'"]

    end = content.find("\n---\n", 4)
    if end == -1:
        return ["SKILL.md frontmatter not closed with '---'"]

    fm_str = content[4:end]
    try:
        fm = yaml.safe_load(fm_str)
    except yaml.YAMLError as exc:
        return [f"Invalid YAML frontmatter: {exc}"]

    if not isinstance(fm, dict):
        return ["Frontmatter must be a YAML mapping"]

    unknown = set(fm.keys()) - ALLOWED_KEYS
    if unknown:
        errors.append(f"Unknown frontmatter keys: {sorted(unknown)}")

    # name
    if "name" not in fm:
        errors.append("Missing required field: name")
    else:
        name = fm["name"]
        if not isinstance(name, str):
            errors.append("name must be a string")
        else:
            if len(name) > MAX_NAME_LEN:
                errors.append(f"name too long: {len(name)} > {MAX_NAME_LEN}")
            if name.endswith("-"):
                errors.append(f"name must not end with a hyphen: {name!r}")
            if "--" in name:
                errors.append(f"name must not contain consecutive hyphens: {name!r}")
            if not NAME_RE.match(name):
                errors.append(f"name must match ^[a-z0-9][a-z0-9-]*$: {name!r}")

    # description
    if "description" not in fm:
        errors.append("Missing required field: description")
    else:
        desc = fm["description"]
        if not isinstance(desc, str):
            errors.append("description must be a string")
        else:
            if len(desc) > MAX_DESC_LEN:
                errors.append(f"description too long: {len(desc)} > {MAX_DESC_LEN}")
            if "<" in desc or ">" in desc:
                errors.append("description must not contain angle brackets")

    # compatibility (optional)
    if "compatibility" in fm:
        compat = fm["compatibility"]
        if not isinstance(compat, str):
            errors.append("compatibility must be a string")
        elif len(compat) > MAX_COMPAT_LEN:
            errors.append(f"compatibility too long: {len(compat)} > {MAX_COMPAT_LEN}")

    # disable-model-invocation (optional): Claude Code key, boolean
    if "disable-model-invocation" in fm and not isinstance(fm["disable-model-invocation"], bool):
        errors.append("disable-model-invocation must be a boolean")

    return errors


def main():
    args = sys.argv[1:]
    allow_path = DEFAULT_SIZE_ALLOW
    if "--size-allow" in args:
        i = args.index("--size-allow")
        allow_path = args[i + 1]
        del args[i:i + 2]
    root = os.path.abspath(args[0] if args else ".")
    skills = sorted(find_skills(root))

    if not skills:
        print("ERROR: no skills found (no directories containing SKILL.md)", file=sys.stderr)
        sys.exit(1)

    allowed, allow_errors = load_size_allow(allow_path)
    for err in allow_errors:
        print(f"ERROR {err}", file=sys.stderr)

    failures = 0
    for skill_dir in skills:
        errors = validate_skill(skill_dir)
        rel = os.path.relpath(skill_dir, root)
        warnings, size_errors = size_findings(skill_dir, rel, allowed)
        errors += size_errors
        if errors:
            failures += 1
            print(f"FAIL {rel}")
            for err in errors:
                print(f"     {err}")
        else:
            print(f"OK   {rel}")
        for warn in warnings:
            print(f"WARN {rel}: {warn}")

    if allow_errors:
        failures += len(allow_errors)

    print(f"\n{len(skills)} skill(s) checked, {failures} failure(s).")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
