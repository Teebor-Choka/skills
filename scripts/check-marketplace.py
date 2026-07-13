#!/usr/bin/env python3
"""Validate .claude-plugin/marketplace.json: parse + verify all listed skill paths contain SKILL.md."""

import json
import os
import sys


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
        for skill_path in plugin.get("skills", []):
            full = os.path.normpath(os.path.join(root, skill_path))
            skill_md = os.path.join(full, "SKILL.md")
            if not os.path.isfile(skill_md):
                errors.append(f"plugin {plugin_name!r}: missing SKILL.md at {skill_path}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    skill_count = sum(len(p.get("skills", [])) for p in plugins)
    print(f"marketplace.json OK — {len(plugins)} plugin(s), {skill_count} skill(s)")


if __name__ == "__main__":
    main()
