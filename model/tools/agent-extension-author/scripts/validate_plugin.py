#!/usr/bin/env python3
"""Fast, dependency-free checks for a portable Agent Plugins bundle.

Usage: validate_plugin.py <plugin-dir> [<plugin-dir> ...]

Validates the portable plugin contract (agent-plugins.org) that Claude Code, Codex, OpenCode,
and oh-my-pi build their native plugin mechanisms on:
- plugin.json exists at the plugin root and is valid JSON.
- name: required, ^[a-z0-9][a-z0-9-]*$, <=64 chars.
- $schema: present and points at an agent-plugins.org schema (portable).
- version: if present, looks like a dotted version.
- each skills/<name>/ holds a SKILL.md (delegated detail is in validate_skill.py).
Warnings (do not fail the build) flag portability risks:
- a top-level manifest key outside the portable set that is not a reverse-domain extension
  namespace (e.g. a bare "openai" block instead of extensions.com.openai).
- a vendor overlay present with no portable core alongside it.

Exit code 0 if every plugin passes the hard checks (warnings allowed), else 1.
Uses only the standard library, so it runs anywhere Python 3 does.
"""
import json
import os
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VERSION_RE = re.compile(r"^\d+(\.\d+)+")
# Portable top-level keys per the Agent Plugins schema (superset; extras are warned, not failed).
PORTABLE_KEYS = {"$schema", "name", "version", "description", "author", "license",
                 "homepage", "keywords", "metadata", "mcpServers", "extensions"}
VENDOR_OVERLAYS = [".claude-plugin/plugin.json", ".codex-plugin/plugin.json"]


def validate(plugin_dir):
    errors, warnings = [], []
    manifest = os.path.join(plugin_dir, "plugin.json")
    if not os.path.isfile(manifest):
        # A vendor overlay without a portable root manifest is a portability smell, not a hard fail.
        overlay = next((o for o in VENDOR_OVERLAYS if os.path.isfile(os.path.join(plugin_dir, o))), None)
        if overlay:
            return [f"no portable plugin.json in {plugin_dir} (only {overlay}); add a portable root manifest"], []
        return [f"no plugin.json in {plugin_dir}"], []

    with open(manifest, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            return [f"plugin.json is not valid JSON: {e}"], []
    if not isinstance(data, dict):
        return ["plugin.json must be a JSON object"], []

    name = data.get("name")
    if not name:
        errors.append("missing required field: name")
    elif not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
        errors.append(f"name must match ^[a-z0-9][a-z0-9-]*$ and be <=64 chars: {name!r}")

    schema = data.get("$schema")
    if not schema:
        warnings.append("no $schema — set it to an agent-plugins.org schema so the manifest is portable")
    elif "agent-plugins.org" not in str(schema):
        warnings.append(f"$schema is not an agent-plugins.org URL ({schema!r}) — may not be portable")

    version = data.get("version")
    if version is not None and not VERSION_RE.match(str(version)):
        warnings.append(f"version {version!r} does not look like a dotted version")

    for k in data:
        if k in PORTABLE_KEYS:
            continue
        # A reverse-domain namespace (has a dot, e.g. com.openai.foo) is the sanctioned overlay form.
        if "." in k:
            continue
        warnings.append(f"non-portable top-level key {k!r} — move it under a reverse-domain "
                        f"extension namespace (e.g. extensions.com.<vendor>), not the portable core")

    skills_dir = os.path.join(plugin_dir, "skills")
    if os.path.isdir(skills_dir):
        subs = [d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))]
        for d in subs:
            if not os.path.isfile(os.path.join(skills_dir, d, "SKILL.md")):
                errors.append(f"skills/{d}/ has no SKILL.md")
        if not subs:
            warnings.append("skills/ exists but is empty")

    return errors, warnings


def main():
    if len(sys.argv) < 2:
        sys.exit(f"usage: {sys.argv[0]} <plugin-dir> [<plugin-dir> ...]")
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
    print(f"\n{len(sys.argv) - 1} plugin(s) checked, {failed} failure(s).")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
