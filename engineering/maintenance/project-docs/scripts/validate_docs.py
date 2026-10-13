#!/usr/bin/env python3
"""Validate a project's docs/ tree against the project-docs contract.

Single source of truth for every rule here is references/contract.md. This script
enforces the mechanical half of that contract; it never judges content quality.
Standard library only (no pyyaml): the frontmatter is flat `key: value` pairs plus
occasional `[a, b]` lists, parsed inline.

A "project" is any coherent unit of work: a code repo, a subproject, or a non-code
effort. The validator treats a project as a directory holding a docs/ tree.

Usage:
    validate_docs.py <project-path>           validate one project
    validate_docs.py --all <root-path>        validate every project found under root
    validate_docs.py <project-path> --json    machine-readable findings

Exit code 0 only when every checked project passes; nonzero if any finding is raised.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# --- contract constants (references/contract.md) -----------------------------

ADR_STATUSES = frozenset({"proposed", "accepted", "superseded", "rejected"})
UPDATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MERMAID_RE = re.compile(r"(?m)^[ \t]*`{3,}[ \t]*mermaid\b")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# ADR body must contain all four labels; the last is satisfied by any one of the set.
ADR_REQUIRED_LABELS = ("Context", "Decision", "Consequences")
ADR_SETASIDE_LABELS = ("Set aside", "Alternatives", "Rejected")

# The project-name key is `project`; `repo` is a deprecated alias still accepted.
NAME_KEY = "project"
NAME_ALIAS = "repo"

# Required frontmatter keys per kind. ADRs (kind None) require status instead of kind.
# NAME_KEY is satisfied by either `project` or the `repo` alias (see _name_value).
REQUIRED_KEYS = {
    "overview": ("title", "kind", NAME_KEY, "updated"),
    "spec": ("title", "kind", NAME_KEY, "updated"),
    "decisions-index": ("title", "kind", NAME_KEY, "updated"),
    None: ("title", "status", NAME_KEY, "updated"),  # ADR
}


@dataclass
class Finding:
    project: str
    file: str | None
    rule: str
    message: str
    severity: str = "error"


# --- frontmatter parsing -----------------------------------------------------


def split_frontmatter(text: str) -> tuple[dict[str, object] | None, str]:
    """Return (frontmatter_dict, body). frontmatter_dict is None when the file
    does not open with a `---` ... `---` block. Body is the text after it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = _parse_flat_yaml(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return fm, body
    # Opened a block but never closed it: treat as missing frontmatter.
    return None, text


def _parse_flat_yaml(lines: list[str]) -> dict[str, object]:
    out: dict[str, object] = {}
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = _parse_scalar(value.strip())
    return out


def _parse_scalar(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_unquote(v.strip()) for v in inner.split(",")]
    return _unquote(value)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _name_value(fm: dict[str, object]) -> str | None:
    """The project name from frontmatter: `project`, falling back to the `repo`
    alias. Returns None when neither is a non-empty string."""
    for key in (NAME_KEY, NAME_ALIAS):
        val = fm.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


# --- per-project validation --------------------------------------------------


def validate_project(project_path: Path, project_label: str | None = None) -> list[Finding]:
    project = project_label or project_path.name or str(project_path)
    findings: list[Finding] = []
    docs = project_path / "docs"

    if not docs.is_dir():
        return [Finding(project, None, "undocumented", "no docs/ directory", "warning")]

    overview = docs / "overview.md"
    spec = docs / "spec.md"
    decisions = docs / "decisions"
    index = decisions / "README.md"

    # --- tree --------------------------------------------------------------
    if not overview.is_file():
        findings.append(Finding(project, "docs/overview.md", "missing-overview",
                                "docs/overview.md is required but missing"))
    if not index.is_file():
        findings.append(Finding(project, "docs/decisions/README.md", "missing-decisions-index",
                                "docs/decisions/README.md is required but missing"))

    adr_files = sorted(
        p for p in decisions.glob("*.md") if p.name != "README.md"
    ) if decisions.is_dir() else []
    if not adr_files:
        findings.append(Finding(project, "docs/decisions/", "missing-adr",
                                "docs/decisions needs at least one ADR besides README.md"))

    # --- frontmatter (known docs only; extra docs are ignored per contract) ---
    name_values: dict[str, str] = {}  # relpath -> project value, for divergence check

    known: list[tuple[Path, str | None]] = []
    if overview.is_file():
        known.append((overview, "overview"))
    if spec.is_file():
        known.append((spec, "spec"))
    if index.is_file():
        known.append((index, "decisions-index"))
    for adr in adr_files:
        known.append((adr, None))  # ADR

    for path, expected_kind in known:
        rel = path.relative_to(project_path).as_posix()
        text = path.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(text)
        if fm is None:
            findings.append(Finding(project, rel, "frontmatter-missing",
                                    "missing YAML frontmatter block (--- ... ---)"))
            continue

        for key in REQUIRED_KEYS[expected_kind]:
            if key == NAME_KEY:
                if _name_value(fm) is None:
                    findings.append(Finding(project, rel, "frontmatter-key",
                                            f"missing or empty required frontmatter key: {NAME_KEY}"
                                            f" (or its {NAME_ALIAS!r} alias)"))
                continue
            val = fm.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                findings.append(Finding(project, rel, "frontmatter-key",
                                        f"missing or empty required frontmatter key: {key}"))

        if expected_kind is not None:
            kind = fm.get("kind")
            if kind is not None and kind != expected_kind:
                findings.append(Finding(project, rel, "frontmatter-kind",
                                        f"kind is {kind!r}, expected {expected_kind!r}"))

        updated = fm.get("updated")
        if isinstance(updated, str) and updated.strip() and not UPDATED_RE.match(updated):
            findings.append(Finding(project, rel, "frontmatter-updated",
                                    f"updated {updated!r} is not an ISO date YYYY-MM-DD"))

        if expected_kind is None:
            status = fm.get("status")
            if isinstance(status, str) and status.strip() and status not in ADR_STATUSES:
                findings.append(Finding(project, rel, "frontmatter-status",
                                        f"status {status!r} not one of "
                                        f"{sorted(ADR_STATUSES)}"))

        name_val = _name_value(fm)
        if name_val is not None:
            name_values[rel] = name_val

    # --- project value must be identical across all docs -------------------
    findings.extend(_check_name_divergence(project, name_values))

    # --- ADR filename + sections -------------------------------------------
    for adr in adr_files:
        rel = adr.relative_to(project_path).as_posix()
        slug = adr.stem
        if not KEBAB_RE.match(slug):
            findings.append(Finding(project, rel, "adr-filename",
                                    f"ADR filename {slug!r} is not kebab-case "
                                    r"(^[a-z0-9]+(-[a-z0-9]+)*$)"))
        _, body = split_frontmatter(adr.read_text(encoding="utf-8"))
        findings.extend(_check_adr_sections(project, rel, body))

    # --- decisions index, both directions ----------------------------------
    if index.is_file():
        findings.extend(_check_index(project, project_path, index, decisions, adr_files))

    # --- AGENTS.md pointer -------------------------------------------------
    findings.extend(_check_agents(project, project_path))

    # --- diagrams ----------------------------------------------------------
    if overview.is_file() and not MERMAID_RE.search(overview.read_text(encoding="utf-8")):
        findings.append(Finding(project, "docs/overview.md", "diagram",
                                "overview.md has no ```mermaid block"))
    if spec.is_file() and not MERMAID_RE.search(spec.read_text(encoding="utf-8")):
        findings.append(Finding(project, "docs/spec.md", "diagram",
                                "spec.md has no ```mermaid block"))

    return findings


def _check_name_divergence(project: str, name_values: dict[str, str]) -> list[Finding]:
    distinct = set(name_values.values())
    if len(distinct) <= 1:
        return []
    # Canonical = overview's value if present, else the most common.
    canonical = name_values.get("docs/overview.md")
    if canonical is None:
        canonical = max(distinct, key=lambda v: list(name_values.values()).count(v))
    out = []
    for rel, val in sorted(name_values.items()):
        if val != canonical:
            out.append(Finding(project, rel, "project-divergence",
                               f"project is {val!r}, diverges from {canonical!r} used elsewhere"))
    return out


def _check_adr_sections(project: str, rel: str, body: str) -> list[Finding]:
    out = []
    for label in ADR_REQUIRED_LABELS:
        if not _has_label(body, label):
            out.append(Finding(project, rel, "adr-section",
                               f"ADR body missing {label!r} section "
                               f"(as **{label}.** or ## {label})"))
    if not any(_has_label(body, lbl) for lbl in ADR_SETASIDE_LABELS):
        out.append(Finding(project, rel, "adr-section",
                           "ADR body missing a set-aside section (one of "
                           f"{list(ADR_SETASIDE_LABELS)})"))
    return out


def _has_label(body: str, label: str) -> bool:
    bold = re.compile(r"\*\*\s*" + re.escape(label) + r"\b")
    heading = re.compile(r"(?m)^#{1,6}\s+" + re.escape(label) + r"\b")
    return bool(bold.search(body) or heading.search(body))


def _check_index(project: str, project_path: Path, index: Path, decisions: Path,
                 adr_files: list[Path]) -> list[Finding]:
    out = []
    text = index.read_text(encoding="utf-8")
    linked = _index_links_in_dir(text)

    # Reverse: every in-dir link resolves to a real file.
    for target in sorted(linked):
        if not (decisions / target).is_file():
            out.append(Finding(project, "docs/decisions/README.md", "index-drift",
                               f"index links {target!r} but no such file exists"))

    # Forward: every ADR is linked from the index.
    for adr in adr_files:
        if adr.name not in linked:
            rel = adr.relative_to(project_path).as_posix()
            out.append(Finding(project, rel, "index-drift",
                               f"{adr.name} is not linked from decisions/README.md"))
    return out


def _index_links_in_dir(text: str) -> set[str]:
    """Link targets that point at a *.md file in the same directory (bare name
    or ./name), with any anchor stripped. Links to other dirs are skipped."""
    out: set[str] = set()
    for target in LINK_RE.findall(text):
        t = target.split("#", 1)[0].strip()
        if t.startswith("./"):
            t = t[2:]
        if not t.endswith(".md") or "/" in t:
            continue
        out.add(t)
    return out


def _check_agents(project: str, project_path: Path) -> list[Finding]:
    agents = project_path / "AGENTS.md"
    if not agents.is_file():
        return [Finding(project, "AGENTS.md", "agents-md",
                        "root AGENTS.md is required but missing")]
    text = agents.read_text(encoding="utf-8")
    out = []
    for needle in ("docs/overview.md", "docs/decisions"):
        if needle not in text:
            out.append(Finding(project, "AGENTS.md", "agents-md",
                               f"AGENTS.md does not mention {needle!r}"))
    return out


# --- project discovery -------------------------------------------------------


def find_projects(root: Path) -> list[Path]:
    """Every dir under root that holds a docs/ dir OR a .git entry. A detected
    project is not descended into, so docs/decisions and nested workdirs are not
    mistaken for separate projects."""
    projects: list[Path] = []
    skip = {"node_modules", ".direnv", "target", "result", "__pycache__"}
    for dirpath, dirnames, _ in os.walk(root):
        d = Path(dirpath)
        if (d / "docs").is_dir() or (d / ".git").exists():
            projects.append(d)
            dirnames[:] = []  # prune: do not descend into a detected project
            continue
        dirnames[:] = [n for n in dirnames if n not in skip and not n.startswith(".")]
    return sorted(projects)


# --- CLI ---------------------------------------------------------------------


def _format_line(f: Finding) -> str:
    where = f"{f.project}/{f.file}" if f.file else f.project
    return f"{where}: {f.message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate project docs against the contract.")
    parser.add_argument("path", help="project path, or root path with --all")
    parser.add_argument("--all", action="store_true",
                        help="treat path as a root and validate every project under it")
    parser.add_argument("--json", action="store_true", help="machine-readable findings")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"error: path does not exist: {root}", file=sys.stderr)
        return 2

    if args.all:
        projects = find_projects(root)
    else:
        projects = [root]

    all_findings: list[Finding] = []
    per_project: list[tuple[str, int]] = []
    for project_path in projects:
        label = (project_path.relative_to(root).as_posix() if args.all and project_path != root
                 else project_path.name or str(project_path))
        if args.all and label == ".":
            label = project_path.name or str(project_path)
        findings = validate_project(project_path, project_label=label)
        all_findings.extend(findings)
        per_project.append((label, len(findings)))

    if args.json:
        print(json.dumps([asdict(f) for f in all_findings], indent=2))
    else:
        for f in all_findings:
            print(_format_line(f))
        if args.all:
            print("", file=sys.stderr)
            for label, n in per_project:
                status = "PASS" if n == 0 else f"FAIL ({n})"
                print(f"{status:<10} {label}", file=sys.stderr)
        if not all_findings:
            print("ok: all checks passed", file=sys.stderr)

    return 0 if not all_findings else 1


if __name__ == "__main__":
    sys.exit(main())
