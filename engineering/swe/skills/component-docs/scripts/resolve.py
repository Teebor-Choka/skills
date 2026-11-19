#!/usr/bin/env python3
"""Resolve a project's components for component-docs, and optionally scaffold their pages.

Finds the docs tooling's components.py and runs it, passing its stdout and exit code through
unchanged: 0 resolved, 2 unreadable input, 3 needs-input. When the tooling cannot be found, or
(with --scaffold) the project name cannot be read, it halts the same way: one JSON object on stdout,
exit 3, nothing written. It never prompts; --interactive is passed to the resolver as given.

Usage:
    resolve.py [project] [--project-docs DIR] [--scaffold] [--components GLOB ...] [--interactive]

--scaffold writes docs/components/<page>.md from the tooling's skeleton for each resolved component
that has no page, with frontmatter filled from the resolver. It never overwrites a page.
Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOL = "resolve.py"
HERE = Path(__file__).resolve()
# Beside this plugin in the marketplace layout, then the usual user-level install paths.
STANDARD = (HERE.parents[4] / "design" / "skills" / "project-docs",
            Path("~/.config/agents/skills/project-docs"),
            Path("~/.claude/skills/project-docs"),
            Path("~/.agents/skills/project-docs"))


def halt(field: str, reason: str, supply: list[str]) -> int:
    print(json.dumps({"status": "needs-input", "tool": TOOL,
                      "missing": [{"field": field, "reason": reason, "supply": supply}]}, indent=2))
    return 3


def locate(explicit: str | None) -> Path | None:
    """The docs tooling directory: the flag, else $PROJECT_DOCS_DIR, else a standard path. An explicit
    choice that is wrong is not replaced by a default."""
    chosen = explicit or os.environ.get("PROJECT_DOCS_DIR")
    candidates = [Path(chosen).expanduser()] if chosen else [p.expanduser() for p in STANDARD]
    return next((c for c in candidates if (c / "scripts" / "components.py").is_file()), None)


def project_name(project: Path) -> str | None:
    try:
        text = (project / "docs" / "overview.md").read_text(encoding="utf-8")
    except OSError:
        return None
    head = text.split("---", 2)[1] if text.startswith("---") else ""
    match = re.search(r"^(?:project|repo):\s*[\"']?([^\"'\n#]+?)[\"']?\s*(?:#.*)?$", head, re.M)
    return match.group(1) if match else None


def page_stem(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", name)  # same rule as components.page_name


def fill(skeleton: str, name: str, project: str, path: str, depends: list[str]) -> str:
    front, sep, rest = skeleton.partition("\n---\n")
    for old, new in (("title: COMPONENT", f"title: {name}"), ("project: PROJECT", f"project: {project}"),
                     ("updated: YYYY-MM-DD", f"updated: {datetime.date.today().isoformat()}"),
                     ("component: COMPONENT", f"component: {name}"), ("path: DIR", f"path: {path}"),
                     ("depends-on: []", f"depends-on: [{', '.join(depends)}]")):
        front = front.replace(old, new, 1)
    return front + sep + rest.replace("# COMPONENT", f"# {name}", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--project-docs", metavar="DIR", help="the docs tooling directory")
    parser.add_argument("--scaffold", action="store_true")
    args, passthrough = parser.parse_known_args()

    tooling = locate(args.project_docs)
    if tooling is None:
        return halt("project-docs", "the docs tooling (scripts/components.py) was not found",
                    ["--project-docs <dir>", "PROJECT_DOCS_DIR=<dir>"])
    run = subprocess.run([sys.executable, str(tooling / "scripts" / "components.py"), args.path, *passthrough],
                         stdout=subprocess.PIPE, text=True)
    if run.returncode != 0 or not args.scaffold:
        sys.stdout.write(run.stdout)
        return run.returncode

    project = Path(args.path)
    missing = [c for c in json.loads(run.stdout)["components"]
               if not (project / "docs" / "components" / f"{page_stem(c['name'])}.md").exists()]
    name = project_name(project) if missing else ""
    if name is None:
        return halt("project", "docs/overview.md has no project: key to copy into the pages",
                    ["docs/overview.md frontmatter project:"])
    sys.stdout.write(run.stdout)
    skeleton = (tooling / "assets" / "component.skeleton.md").read_text(encoding="utf-8")
    for c in missing:
        target = project / "docs" / "components" / f"{page_stem(c['name'])}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fill(skeleton, c["name"], name, c["path"], c["depends-on"]), encoding="utf-8")
        print(f"wrote {target.relative_to(project).as_posix()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
