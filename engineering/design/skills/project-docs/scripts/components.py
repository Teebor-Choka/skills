#!/usr/bin/env python3
"""Resolve a project's components from its manifests (references/contract.md, "Components").

A component is a Cargo workspace member, an npm/yarn workspace package, a uv workspace member or
single pyproject package, or a Go module (go.work member or single go.mod). `docs.components.include`
(or --components) replaces discovery with declared directories, which may be modules without a manifest.
When the workspace format cannot be read with the standard library, the run halts with `needs-input`
and exit 3; it never guesses from the directory tree.

Standard library only; `tomllib` (Python 3.11+) is imported only to parse a TOML manifest.

Usage:
    components.py [project-path] [--components GLOB ...] [--interactive]

stdout is one JSON object. Exit 0 resolved, 2 unreadable input, 3 needs-input.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TOOL = "components.py"
# What a caller can supply when the components cannot be determined. The validator reuses it.
SUPPLY = ("--components 'packages/*'", ".agents/policy docs.components.include")
# Workspace formats the standard library cannot parse; one of these without an include list halts.
UNSUPPORTED = ("pnpm-workspace.yaml", "WORKSPACE", "WORKSPACE.bazel", "MODULE.bazel",
               "settings.gradle", "settings.gradle.kts")
GLOB_CHARS = "*?["


@dataclass(frozen=True)
class Component:
    name: str
    path: str  # repo-relative POSIX dir; "." for the repo root
    depends_on: tuple[str, ...]  # internal dependencies by component name, codepoint-sorted
    source: str  # "manifest" or "module"


class NeedsInput(Exception):
    def __init__(self, missing: list[dict]) -> None:
        super().__init__("needs-input")
        self.missing = missing


class ManifestError(Exception):
    """An unreadable manifest or policy file; the message names the file."""


@dataclass
class _Raw:
    name: str
    ident: str  # what another component's dependency list calls this one
    deps: set[str]
    path: str
    source: str = "manifest"


def page_name(name: str) -> str:
    """The file stem of a component's page: characters outside [a-z0-9-] become '-'."""
    return re.sub(r"[^a-z0-9-]", "-", name)


def _norm(ident: str) -> str:
    return re.sub(r"[-_.]+", "-", ident.lower())


# --- policy (.agents/policy.md; the subset of the shared loader's format this tool needs) ---------


def _strip_comment(value: str) -> str:
    depth, quote = 0, None
    for i, c in enumerate(value):
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c in "[({":
            depth += 1
        elif c in "])}":
            depth = max(0, depth - 1)
        elif c == "#" and depth == 0 and (i == 0 or value[i - 1].isspace()):
            return value[:i].strip()
    return value.strip()


def _unquote(value: str) -> str:
    value = value.strip()
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value


def read_policy(project: Path) -> dict:
    """Frontmatter of .agents/policy.md as nested dicts: scalars, inline lists, maps by indentation.
    Only the project's own file is read; the global layer is not."""
    path = project / ".agents" / "policy.md"
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ManifestError(".agents/policy.md: no frontmatter block")
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for n, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            return root
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ManifestError(f".agents/policy.md:{n}: not a 'key: value' line")
        indent = len(line) - len(line.lstrip())
        raw_key, _, raw_val = line.lstrip().partition(":")
        val = _strip_comment(raw_val)
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        key = _unquote(raw_key)
        if val == "":
            parent[key] = {}
            stack.append((indent, parent[key]))
        elif val.startswith("["):
            inner = val[1:-1].strip() if val.endswith("]") else ""
            parent[key] = [_unquote(x) for x in inner.split(",") if x.strip()]
        else:
            parent[key] = _unquote(val)
    raise ManifestError(".agents/policy.md: unterminated frontmatter")


def policy_options(project: Path) -> tuple[list[str] | None, dict[str, str]]:
    """(docs.components.include or None, docs.components.exclude as {name: reason})."""
    node = read_policy(project).get("docs", {})
    node = node.get("components", {}) if isinstance(node, dict) else {}
    include = node.get("include") if isinstance(node, dict) else None
    if isinstance(include, str):
        include = [include]
    exclude = node.get("exclude") if isinstance(node, dict) else None
    return (include or None), (exclude if isinstance(exclude, dict) else {})


# --- manifests -------------------------------------------------------------------------------------


class _Repo:
    """Reads manifests under one project root, each file at most once."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, object] = {}

    def has(self, rel: str, fname: str) -> bool:
        return (self.root / rel / fname).is_file()

    def _load(self, rel: str, fname: str, parse) -> object:
        label = fname if rel == "." else f"{rel}/{fname}"
        if label not in self._cache:
            try:
                self._cache[label] = parse(self.root / rel / fname, label)
            except OSError as exc:
                raise ManifestError(f"{label}: unreadable ({exc.strerror})") from exc
        return self._cache[label]

    def toml(self, rel: str, fname: str) -> dict:
        def parse(path: Path, label: str) -> dict:
            try:
                import tomllib  # Python 3.11+, needed only for a TOML manifest
            except ImportError:
                raise ManifestError(f"python 3.11+ required to parse {label}") from None
            try:
                with open(path, "rb") as fh:
                    return tomllib.load(fh)
            except tomllib.TOMLDecodeError as exc:
                raise ManifestError(f"{label}: invalid TOML ({exc})") from exc

        return self._load(rel, fname, parse)  # type: ignore[return-value]

    def json(self, rel: str, fname: str) -> dict:
        def parse(path: Path, label: str) -> dict:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ManifestError(f"{label}: invalid JSON ({exc})") from exc
            if not isinstance(data, dict):
                raise ManifestError(f"{label}: expected a JSON object")
            return data

        return self._load(rel, fname, parse)  # type: ignore[return-value]

    def text(self, rel: str, fname: str) -> str:
        return self._load(rel, fname, lambda p, _l: p.read_text(encoding="utf-8", errors="replace"))  # type: ignore[return-value]


def _expand(root: Path, patterns: list[str]) -> list[str]:
    """Directories matching the patterns, as sorted POSIX relpaths. A segment with glob characters
    is matched with fnmatch over directory names; the root is ".". Dot-directories are skipped."""
    found: set[str] = set()
    for pattern in patterns:
        segs = [s for s in pattern.strip().strip("/").split("/") if s not in ("", ".")]
        current = [""]
        for seg in segs:
            nxt: list[str] = []
            for base in current:
                here = root / base
                if any(c in seg for c in GLOB_CHARS):
                    try:
                        names = sorted(os.listdir(here))
                    except OSError:
                        continue
                    nxt += [f"{base}/{n}".lstrip("/") for n in names
                            if not n.startswith(".") and fnmatch.fnmatchcase(n, seg) and (here / n).is_dir()]
                elif (here / seg).is_dir():
                    nxt.append(f"{base}/{seg}".lstrip("/"))
            current = nxt
        found.update(c or "." for c in current)
    return sorted(found)


def _cargo(repo: _Repo, rel: str) -> _Raw | None:
    if not repo.has(rel, "Cargo.toml"):
        return None
    data = repo.toml(rel, "Cargo.toml")
    pkg = data.get("package")
    if not isinstance(pkg, dict) or not pkg.get("name"):
        return None
    tables = [data.get("dependencies", {})]
    tables += [t.get("dependencies", {}) for t in data.get("target", {}).values() if isinstance(t, dict)]
    deps = {_norm(spec["package"] if isinstance(spec, dict) and "package" in spec else key)
            for table in tables if isinstance(table, dict) for key, spec in table.items()}
    return _Raw(pkg["name"], _norm(pkg["name"]), deps, rel)


def _npm(repo: _Repo, rel: str) -> _Raw | None:
    if not repo.has(rel, "package.json"):
        return None
    data = repo.json(rel, "package.json")
    name = data.get("name")
    if not isinstance(name, str) or not name:
        return None
    deps = {_norm(d) for k in ("dependencies", "optionalDependencies")
            if isinstance(data.get(k), dict) for d in data[k]}
    return _Raw(name, _norm(name), deps, rel)


def _py(repo: _Repo, rel: str) -> _Raw | None:
    if not repo.has(rel, "pyproject.toml"):
        return None
    project = repo.toml(rel, "pyproject.toml").get("project")
    if not isinstance(project, dict) or not project.get("name"):
        return None
    deps = set()
    for req in project.get("dependencies", []):
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(req).strip())
        if m:
            deps.add(_norm(m.group()))
    return _Raw(project["name"], _norm(project["name"]), deps, rel)


def _go(repo: _Repo, rel: str) -> _Raw | None:
    if not repo.has(rel, "go.mod"):
        return None
    text = re.sub(r"//.*", "", repo.text(rel, "go.mod"))
    mod = re.search(r"(?m)^\s*module\s+(\S+)", text)
    if not mod:
        return None
    path = mod.group(1).strip('"')
    requires = re.findall(r"(?m)^\s*require\s+(\S+)\s+v\S+", text)
    for block in re.findall(r"(?ms)^\s*require\s*\((.*?)^\s*\)", text):
        requires += re.findall(r"(?m)^\s*(\S+)\s+v\S+", block)
    return _Raw(path.rstrip("/").rsplit("/", 1)[-1], _norm(path), {_norm(r) for r in requires}, rel)


MANIFESTS = (_cargo, _npm, _py, _go)


def _package_at(repo: _Repo, rel: str) -> _Raw | None:
    for read in MANIFESTS:
        raw = read(repo, rel)
        if raw is not None:
            return raw
    return None


def _members(repo: _Repo, read, patterns: list[str], exclude: list[str]) -> list[_Raw]:
    skip = set(_expand(repo.root, exclude))
    return [r for rel in _expand(repo.root, patterns) if rel not in skip
            if (r := read(repo, rel)) is not None]


def _discover(repo: _Repo) -> list[_Raw]:
    raws: list[_Raw] = []
    if repo.has(".", "Cargo.toml"):
        data = repo.toml(".", "Cargo.toml")
        ws = data.get("workspace")
        if isinstance(ws, dict):
            raws += _members(repo, _cargo, ws.get("members", []), ws.get("exclude", []))
        if "package" in data and (r := _cargo(repo, ".")):
            raws.append(r)
    if repo.has(".", "package.json"):
        data = repo.json(".", "package.json")
        ws = data.get("workspaces")
        patterns = ws.get("packages", []) if isinstance(ws, dict) else ws
        if isinstance(patterns, list):
            keep = [p for p in patterns if not p.startswith("!")]
            raws += _members(repo, _npm, keep, [p[1:] for p in patterns if p.startswith("!")])
        elif (r := _npm(repo, ".")):
            raws.append(r)
    if repo.has(".", "pyproject.toml"):
        data = repo.toml(".", "pyproject.toml")
        ws = data.get("tool", {}).get("uv", {}).get("workspace")
        if isinstance(ws, dict):
            raws += _members(repo, _py, ws.get("members", []), ws.get("exclude", []))
        if "project" in data and (r := _py(repo, ".")):
            raws.append(r)
    if repo.has(".", "go.work"):
        uses = re.findall(r"(?m)^\s*use\s+(\S+)\s*$", repo.text(".", "go.work"))
        for block in re.findall(r"(?ms)^\s*use\s*\((.*?)^\s*\)", repo.text(".", "go.work")):
            uses += re.findall(r"(?m)^\s*(\S+)\s*$", block)
        raws += _members(repo, _go, [u.strip('"') for u in uses], [])
    elif (r := _go(repo, ".")):
        raws.append(r)
    return raws


def resolve(project: Path, include: list[str] | None = None,
            exclude: dict[str, str] | None = None) -> list[Component]:
    """The project's components, sorted by codepoint of the POSIX relpath. `include` and `exclude`
    default to the policy keys docs.components.include and docs.components.exclude."""
    project = Path(project)
    if not project.is_dir():
        raise ManifestError(f"{project}: not a directory")
    policy_include, policy_exclude = (None, {}) if include is not None and exclude is not None \
        else policy_options(project)
    include = include if include is not None else policy_include
    exclude = exclude if exclude is not None else policy_exclude
    repo = _Repo(project)

    if include:
        raws = []
        for rel in _expand(project, include):
            raw = _package_at(repo, rel)
            if raw is None:
                base = project.resolve().name if rel == "." else rel.rsplit("/", 1)[-1]
                raw = _Raw(base, _norm(base), set(), rel, "module")
            raws.append(raw)
    else:
        for marker in UNSUPPORTED:
            if (project / marker).is_file():
                raise NeedsInput([{"field": "components",
                                   "reason": f"{marker} is not parseable with the Python stdlib",
                                   "supply": list(SUPPLY)}])
        raws = _discover(repo)

    raws = sorted((r for r in raws if r.name not in exclude), key=lambda r: r.path)
    by_ident: dict[str, _Raw] = {}
    seen: dict[str, _Raw] = {}
    for r in raws:
        if r.name in seen:
            raise ManifestError(f"duplicate component name {r.name!r}: {seen[r.name].path} and {r.path}")
        seen[r.name] = r
        by_ident[r.ident] = r
    return [Component(r.name, r.path,
                      tuple(sorted({by_ident[d].name for d in r.deps if d in by_ident and by_ident[d] is not r})),
                      r.source)
            for r in raws]


# --- CLI -------------------------------------------------------------------------------------------


def needs_input_result(exc: NeedsInput) -> dict:
    return {"status": "needs-input", "tool": TOOL, "missing": exc.missing}


def _ask(exc: NeedsInput) -> list[str] | None:
    """Turn the components question into a prompt on stderr; None when nothing usable is answered."""
    for item in exc.missing:
        if item["field"] == "components":
            sys.stderr.write(f"{item['reason']}.\nComponent directories (comma-separated globs): ")
            sys.stderr.flush()
            answer = [g.strip() for g in sys.stdin.readline().split(",") if g.strip()]
            return answer or None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve a project's components.")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--components", action="append", metavar="GLOB",
                        help="declare the components, replacing manifest discovery")
    parser.add_argument("--interactive", action="store_true",
                        help="ask for what is missing instead of halting")
    args = parser.parse_args(argv)
    try:
        try:
            found = resolve(Path(args.path), include=args.components)
        except NeedsInput as exc:
            answer = _ask(exc) if args.interactive else None
            if answer is None:
                print(json.dumps(needs_input_result(exc), indent=2))
                return 3
            found = resolve(Path(args.path), include=answer)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "ok", "components": [
        {"name": c.name, "path": c.path, "depends-on": list(c.depends_on), "source": c.source}
        for c in found]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
