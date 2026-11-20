#!/usr/bin/env python3
"""Validate .claude-plugin/marketplace.json: parse, and verify each plugin source has a matching
plugin.json and at least one skills/<name>/SKILL.md or a hooks/hooks.json (plus any explicit `skills` paths)."""

import glob
import json
import os
import sys


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_hooks(plugin_name, src):
    """Errors for a plugin's hooks/: hooks.json and manifest.json come as a pair, both non-empty."""
    hooks_json = os.path.join(src, "hooks", "hooks.json")
    manifest = os.path.join(src, "hooks", "manifest.json")
    has_json, has_manifest = os.path.isfile(hooks_json), os.path.isfile(manifest)
    if not (has_json or has_manifest):
        return []
    errors = []
    if has_json:
        try:
            events = load_json(hooks_json).get("hooks")
            if not (isinstance(events, dict) and events):
                errors.append(f"plugin {plugin_name!r}: hooks/hooks.json needs a non-empty `hooks` object")
        except (OSError, ValueError, AttributeError):
            errors.append(f"plugin {plugin_name!r}: hooks/hooks.json is not valid JSON object")
    else:
        errors.append(f"plugin {plugin_name!r}: hooks/manifest.json without hooks/hooks.json")
    if has_manifest:
        try:
            entries = load_json(manifest).get("hooks")
            if not (isinstance(entries, list) and entries):
                errors.append(f"plugin {plugin_name!r}: hooks/manifest.json needs a non-empty `hooks` list")
        except (OSError, ValueError, AttributeError):
            errors.append(f"plugin {plugin_name!r}: hooks/manifest.json is not valid JSON object")
    else:
        errors.append(f"plugin {plugin_name!r}: hooks/hooks.json without hooks/manifest.json")
    return errors


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    root = os.path.abspath(root)
    mp = os.path.join(root, ".claude-plugin", "marketplace.json")

    try:
        with open(mp, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {mp} not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in marketplace.json: {exc}", file=sys.stderr)
        sys.exit(1)

    errors = []
    plugins = data.get("plugins", [])

    for plugin in plugins:
        plugin_name = plugin.get("name", "<unnamed>")
        src = os.path.normpath(os.path.join(root, plugin.get("source", "./")))
        if "skills" not in plugin:
            pj = os.path.join(src, ".claude-plugin", "plugin.json")
            try:
                with open(pj, encoding="utf-8") as f:
                    if json.load(f).get("name") != plugin_name:
                        errors.append(f"plugin {plugin_name!r}: plugin.json name differs")
            except (OSError, json.JSONDecodeError):
                errors.append(f"plugin {plugin_name!r}: missing or invalid {pj}")
            errors.extend(check_hooks(plugin_name, src))
            skills = glob.glob(os.path.join(src, "skills", "*", "SKILL.md"))
            if not skills and not os.path.isfile(os.path.join(src, "hooks", "hooks.json")):
                errors.append(f"plugin {plugin_name!r}: no skills/*/SKILL.md under {src}")
        for skill_path in plugin.get("skills", []):
            full = os.path.normpath(os.path.join(root, skill_path))
            skill_md = os.path.join(full, "SKILL.md")
            if not os.path.isfile(skill_md):
                errors.append(f"plugin {plugin_name!r}: missing SKILL.md at {skill_path}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    skill_count = len(glob.glob(os.path.join(root, "**", "skills", "*", "SKILL.md"), recursive=True))
    print(f"marketplace.json OK — {len(plugins)} plugin(s), {skill_count} skill(s)")


if __name__ == "__main__":
    main()
