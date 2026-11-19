#!/usr/bin/env python3
"""Validate a project's docs/ tree against the project-docs contract.

Single source of truth for every rule here is references/contract.md. This script
enforces the mechanical half of that contract; it never judges content quality.
Standard library only (no pyyaml): the frontmatter is flat `key: value` pairs plus
occasional `[a, b]` lists, parsed inline.

A "project" is any coherent unit of work: a code repo, a subproject, or a non-code
effort. The validator treats a project as a directory holding a docs/ tree.

Usage:
    validate_docs.py [project-path]           validate one project (default: current dir)
    validate_docs.py --all <root-path>        validate every project found under root
    validate_docs.py [project-path] --json    machine-readable findings

Exit code 0 only when every checked project passes; 1 if any finding is raised (a finding
labelled "warning" counts too); 2 for a usage error or an unexpected failure.

Where docs/components/ exists, the component-page rules also run. They resolve the components with
components.py, which must sit beside this file. A repo without docs/components/ resolves them only to
raise components-not-adopted (two or more components, `docs.components.adopt` not false); with
components.py absent that check is skipped.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

# --- contract constants (references/contract.md) -----------------------------

# Only active decisions get a file; discarded ones become footnotes (contract.md).
ADR_STATUSES = frozenset({"proposed", "accepted"})
UPDATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Narrow, high-signal credential shapes. Matches are reported by kind only, never echoed.
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"(?<![A-Z0-9])AKIA(?![0-9A-Z]{9}EXAMPLE)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}")),
    ("Slack token", re.compile(r"xox[baprs]-(?:\d{6,}-){2,}[A-Za-z0-9]{10,}")),
)
SUPERSEDE_KEYS = ("supersedes", "superseded-by")

# ADR body must contain these three labels, in this order.
ADR_REQUIRED_LABELS = ("Context", "Decision", "Consequences")
# A label written as a bold lead (**Label.**) or a heading (## Label); the set is
# fixed, so compile each form once.
ADR_LABEL_PATTERNS = {
    label: (
        re.compile(r"\*\*\s*" + re.escape(label) + r"\b"),
        re.compile(r"(?m)^#{1,6}\s+" + re.escape(label) + r"\b"),
    )
    for label in ADR_REQUIRED_LABELS
}
# Footnotes carry discarded/denied alternatives; every reference needs a definition.
FOOTNOTE_DEF_RE = re.compile(r"(?m)^\[\^([^\]]+)\]:")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\](?!:)")

# The project-name key is `project`; `repo` is a deprecated alias still accepted.
NAME_KEYS = ("project", "repo")

# Optional views (docs/views/<name>.html): one self-contained file per source doc, so the only
# thing a view may fetch is nothing. A data: URI and a #fragment are inline, never a fetch.
# Attributes that name a resource, and the ones that run script. The check is deny by default: a
# resource attribute passes only with a data: URI or a #fragment, a handler never passes.
VIEW_URL_ATTRS = frozenset({"src", "poster", "data", "action", "formaction", "xlink:href"})
VIEW_DARK_RE = re.compile(r"prefers-color-scheme\s*:\s*dark")
VIEW_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
VIEW_CSS_IMPORT_RE = re.compile(r"@import\b|image-set\(", re.IGNORECASE)
VIEW_CSS_URL_RE = re.compile(r"url\(\s*['\"]?\s*([^'\")]*)", re.IGNORECASE)

# Component pages (docs/components/<name>.md), checked only where docs/components/ exists.
COMPONENT_KEYS: tuple[object, ...] = ("title", "kind", NAME_KEYS, "updated", "component", "path", "depends-on")
COMPONENT_SECTIONS = ("Purpose", "Structure", "Public API", "Interactions", "Flow", "Decisions")
COMPONENT_MAX_LINES = 200
COMPONENT_MAX_BYTES = 12 * 1024
COMPONENT_API_MAX_ROWS = 25
H2_RE = re.compile(r"^## +(\S.*?)\s*$")
CODE_SPAN_RE = re.compile(r"`([^`]*)`")
API_TOKEN_SPLIT_RE = re.compile(r"::|[{},\s]+")


def _view_inline(value: str) -> bool:
    """True for a value that needs no fetch: a data: URI or a #fragment."""
    v = value.strip().lower()
    return v.startswith(("data:", "#"))


@dataclass(frozen=True)
class DocSpec:
    """One doc kind the contract defines, as data the checks iterate over so the
    frontmatter, kind, and diagram rules all come from one table (contract.md)."""

    relpath: str  # path under docs/
    kind: str  # expected frontmatter `kind`
    requires_mermaid: bool


# Each required key is a name, or a tuple of interchangeable aliases.
FM_KEYS: tuple[object, ...] = ("title", "kind", NAME_KEYS, "updated")
SINGLETON_DOCS = (
    DocSpec("overview.md", "overview", True),
    DocSpec("spec.md", "spec", True),
    DocSpec("process.md", "process", True),
    DocSpec("decisions/README.md", "decisions-index", False),
)
# ADRs have no `kind`; they carry `status` and never require a diagram.
ADR_REQUIRED_KEYS: tuple[object, ...] = ("title", "status", NAME_KEYS, "updated")


@dataclass
class Finding:
    project: str
    file: str | None
    rule: str
    message: str
    severity: str = "error"


# --- small helpers -----------------------------------------------------------


def _present(value: object) -> bool:
    """A frontmatter value counts as present unless it is absent or an empty/blank
    string (a non-string scalar, e.g. a list, counts as present)."""
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _key_satisfied(fm: dict[str, object], key: object) -> bool:
    aliases = key if isinstance(key, tuple) else (key,)
    return any(_present(fm.get(k)) for k in aliases)


def _has_mermaid_block(text: str) -> bool:
    """True when text holds a top-level mermaid fence with a non-blank body. Handles
    ``` and ~~~ fences of any length >= 3; a fence inside another (longer) code
    fence is body text of that fence, not a diagram."""
    opener: tuple[str, int, bool] | None = None  # (char, length, is_mermaid)
    body_has_text = False
    for line in text.splitlines():
        m = FENCE_RE.match(line)
        if opener is None:
            if m:
                marker, info = m.group(1), m.group(2).strip()
                is_mermaid = re.match(r"mermaid\b", info) is not None
                opener, body_has_text = (marker[0], len(marker), is_mermaid), False
        elif m and m.group(1)[0] == opener[0] and len(m.group(1)) >= opener[1] \
                and not m.group(2).strip():
            if opener[2] and body_has_text:
                return True
            opener = None
        elif line.strip():
            body_has_text = True
    return opener is not None and opener[2] and body_has_text  # unclosed fence runs to EOF


def _dir_unreadable(path: Path) -> bool:
    """True when path exists but cannot be listed (e.g. a permission error)."""
    try:
        os.listdir(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return False


def _read(path: Path, project: str, rel: str, findings: list[Finding]) -> str | None:
    """Read a doc as UTF-8; an unreadable file becomes a finding, not a crash."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        findings.append(Finding(project, rel, "unreadable-file",
                                f"unreadable file ({type(exc).__name__})"))
        return None


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
    for key in NAME_KEYS:
        val = fm.get(key)
        if _nonempty_str(val):
            return val.strip()  # type: ignore[union-attr]
    return None


class ToolError(Exception):
    """A failure that is not a finding: the CLI prints it and exits 2."""


# --- per-project validation --------------------------------------------------


def validate_project(project_path: Path, project_label: str | None = None) -> list[Finding]:
    project = project_label or project_path.name or str(project_path)
    findings: list[Finding] = []
    docs = project_path / "docs"

    if _dir_unreadable(docs):
        return [Finding(project, "docs", "unreadable-file", "cannot list docs/")]
    if not docs.is_dir():
        return [Finding(project, None, "undocumented", "no docs/ directory", "warning")]
    if _dir_unreadable(docs / "decisions"):
        return [Finding(project, "docs/decisions", "unreadable-file", "cannot list docs/decisions/")]

    overview = docs / "overview.md"
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

    # --- frontmatter (contract-defined docs only; extras are ignored) ------
    # (path, kind|None for ADR, required_keys). Driven by the doc-kind table above.
    present_specs = [s for s in SINGLETON_DOCS if (docs / s.relpath).is_file()]
    checked: list[tuple[Path, str | None, tuple[object, ...]]] = [
        (docs / s.relpath, s.kind, FM_KEYS) for s in present_specs
    ]
    checked += [(adr, None, ADR_REQUIRED_KEYS) for adr in adr_files]

    texts: dict[Path, str] = {}  # each doc read once, reused below
    bodies: dict[Path, str] = {}  # body after frontmatter, reused for ADR checks
    name_values: dict[str, str] = {}  # relpath -> project value, for divergence
    for path, kind, required in checked:
        rel = path.relative_to(project_path).as_posix()
        text = _read(path, project, rel, findings)
        if text is None:
            continue
        texts[path] = text
        fm, body = split_frontmatter(text)
        bodies[path] = body
        if fm is None:
            findings.append(Finding(project, rel, "frontmatter-missing",
                                    "missing YAML frontmatter block (--- ... ---)"))
            continue

        for key in required:
            if not _key_satisfied(fm, key):
                name = key[0] if isinstance(key, tuple) else key
                alias = f" (or its {key[1]!r} alias)" if isinstance(key, tuple) else ""
                findings.append(Finding(project, rel, "frontmatter-key",
                                        f"missing or empty required frontmatter key: {name}{alias}"))

        if kind is not None:
            actual = fm.get("kind")
            if actual is not None and actual != kind:
                findings.append(Finding(project, rel, "frontmatter-kind",
                                        f"kind is {actual!r}, expected {kind!r}"))
        else:
            status = fm.get("status")
            if _nonempty_str(status) and status not in ADR_STATUSES:
                findings.append(Finding(project, rel, "frontmatter-status",
                                        f"status {status!r} not one of {sorted(ADR_STATUSES)}"))

        updated = fm.get("updated")
        if _nonempty_str(updated) and not _is_iso_date(updated):  # type: ignore[arg-type]
            findings.append(Finding(project, rel, "frontmatter-updated",
                                    f"updated {updated!r} is not an ISO date YYYY-MM-DD"))

        name_val = _name_value(fm)
        if name_val is not None:
            name_values[rel] = name_val

        if kind is None:
            findings.extend(_check_supersede(project, rel, fm, adr_files))

    # --- component pages (only where docs/components/ exists) --------------
    component_pages: dict[str, str] = {}
    comp_dir = docs / "components"
    if comp_dir.is_dir():
        for page in sorted(comp_dir.glob("*.md")):
            rel = page.relative_to(project_path).as_posix()
            text = _read(page, project, rel, findings)
            if text is None:
                continue
            texts[page] = text  # the secret scan below covers pages too
            component_pages[rel] = text
            page_fm = split_frontmatter(text)[0]
            page_name_val = _name_value(page_fm) if page_fm else None
            if page_name_val is not None:
                name_values[rel] = page_name_val

    # --- project value must be identical across all docs -------------------
    findings.extend(_check_name_divergence(project, name_values))
    if comp_dir.is_dir():
        findings.extend(_check_components(project, project_path, component_pages))
    else:
        findings.extend(_check_adoption(project, project_path))

    # --- ADR filename + sections -------------------------------------------
    for adr in adr_files:
        rel = adr.relative_to(project_path).as_posix()
        if not KEBAB_RE.match(adr.stem):
            findings.append(Finding(project, rel, "adr-filename",
                                    f"ADR filename {adr.stem!r} is not kebab-case "
                                    r"(^[a-z0-9]+(-[a-z0-9]+)*$)"))
        if adr in bodies:
            findings.extend(_check_adr_sections(project, rel, bodies[adr]))

    # --- decisions index, both directions ----------------------------------
    if index in texts:
        findings.extend(_check_index(project, project_path, texts[index], decisions, adr_files))

    # --- optional process.md: procedure name and its file ------------------
    process = docs / "process.md"
    if process in texts:
        findings.extend(_check_process(project, project_path, texts[process]))
    else:
        findings.extend(_check_process_required(project, project_path))

    # --- optional views: docs/views/*.html ---------------------------------
    views = docs / "views"
    if _dir_unreadable(views):
        findings.append(Finding(project, "docs/views", "unreadable-file", "cannot list docs/views/"))
    elif views.is_dir():
        for view in sorted(views.glob("*.html")):
            rel = view.relative_to(project_path).as_posix()
            text = _read(view, project, rel, findings)
            if text is not None:
                texts[view] = text  # the secret scan below covers views too
                findings.extend(_check_view(project, project_path, view, rel, text))

    # --- AGENTS.md pointer -------------------------------------------------
    findings.extend(_check_agents(project, project_path))

    # --- diagrams (per the doc-kind table) ---------------------------------
    for spec in present_specs:
        text = texts.get(docs / spec.relpath)
        if spec.requires_mermaid and text is not None and not _has_mermaid_block(text):
            findings.append(Finding(project, f"docs/{spec.relpath}", "diagram",
                                    f"{spec.relpath} has no ```mermaid block with a body"))

    # --- secrets (checked docs only; kind reported, value never echoed) ----
    for path, text in texts.items():
        rel = path.relative_to(project_path).as_posix()
        for kind_name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(project, rel, "secret-pattern",
                                        f"possible {kind_name} found; value not shown"))

    return findings


def _is_iso_date(value: str) -> bool:
    if not UPDATED_RE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_supersede(project: str, rel: str, fm: dict[str, object],
                     adr_files: list[Path]) -> list[Finding]:
    slugs = {p.stem for p in adr_files}
    out = []
    for key in SUPERSEDE_KEYS:
        raw = fm.get(key)
        targets = raw if isinstance(raw, list) else [raw]
        out.extend(
            Finding(project, rel, "adr-supersede",
                    f"{key} names {t!r} but no such ADR exists in docs/decisions")
            for t in targets
            if _nonempty_str(t) and t.strip() not in slugs  # type: ignore[union-attr]
        )
    return out


def _check_name_divergence(project: str, name_values: dict[str, str]) -> list[Finding]:
    if len(set(name_values.values())) <= 1:
        return []
    majority = Counter(name_values.values()).most_common(1)[0][0]
    return [
        Finding(project, rel, "project-divergence",
                f"project is {val!r}, differs from {majority!r} used by the other docs")
        for rel, val in sorted(name_values.items())
        if val != majority
    ]


def _check_adr_sections(project: str, rel: str, body: str) -> list[Finding]:
    out = []
    positions: list[tuple[str, int]] = []
    for label in ADR_REQUIRED_LABELS:
        pos = _label_pos(body, label)
        if pos is None:
            out.append(Finding(project, rel, "adr-section",
                               f"ADR body missing {label!r} section "
                               f"(as **{label}.** or ## {label})"))
        else:
            positions.append((label, pos))

    # Order: only checkable when all labels are present.
    if len(positions) == len(ADR_REQUIRED_LABELS):
        ordered = [lbl for lbl, _ in sorted(positions, key=lambda lp: lp[1])]
        if ordered != list(ADR_REQUIRED_LABELS):
            out.append(Finding(project, rel, "adr-section-order",
                               f"ADR sections are {ordered}, expected "
                               f"{list(ADR_REQUIRED_LABELS)} in order"))

    out.extend(_check_footnotes(project, rel, body))
    return out


def _label_pos(body: str, label: str) -> int | None:
    """Start offset of a section label written as a bold lead (**Label.**) or a
    heading (## Label), or None if absent."""
    bold, heading = ADR_LABEL_PATTERNS[label]
    m = bold.search(body) or heading.search(body)
    return m.start() if m else None


def _check_footnotes(project: str, rel: str, body: str) -> list[Finding]:
    """Discarded/denied alternatives live in footnotes, so every `[^id]` used
    must have a `[^id]:` definition (an undefined footnote renders as raw text)."""
    defined = set(FOOTNOTE_DEF_RE.findall(body))
    referenced = set(FOOTNOTE_REF_RE.findall(body))
    return [
        Finding(project, rel, "adr-footnote",
                f"footnote [^{fid}] is referenced but never defined")
        for fid in sorted(referenced - defined)
    ]


def _check_index(project: str, project_path: Path, index_text: str, decisions: Path,
                 adr_files: list[Path]) -> list[Finding]:
    out = []
    linked = _index_links_in_dir(index_text)

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


PROCEDURE_TIMEOUT = 30  # seconds the procedure validator may take
STANDARD_VALIDATORS = (
    "~/.config/agents/skills/procedure/scripts/validate_procedure.py",
    "~/.claude/skills/procedure/scripts/validate_procedure.py",
    "~/.agents/skills/procedure/scripts/validate_procedure.py",
)


def _procedure_files(project_path: Path) -> list[Path]:
    """The markdown files directly in .agents/procedures/, which is where a project's procedures live."""
    folder = project_path / ".agents" / "procedures"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.md") if p.is_file())


def _check_process_required(project: str, project_path: Path) -> list[Finding]:
    """A project that has a procedure must say in docs/ which one it runs."""
    found = _procedure_files(project_path)
    if not found:
        return []
    names = ", ".join(p.stem for p in found)
    return [Finding(project, "docs/process.md", "process-doc-missing",
                    f"the project has a procedure ({names}) but no docs/process.md to say which one it runs")]


def _procedure_validator() -> Path | None:
    """The procedure skill's validator: PROCEDURE_VALIDATOR if set (empty turns the check off), else
    the standard install paths. None when there is none, and then the content is not checked."""
    env = os.environ.get("PROCEDURE_VALIDATOR")
    if env is not None:
        return Path(env).expanduser() if env and Path(env).expanduser().is_file() else None
    for candidate in STANDARD_VALIDATORS:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return None


def _check_procedure_content(project: str, project_path: Path, name: str) -> list[Finding]:
    """Run the procedure validator on the named file. It runs as a subprocess with no environment and no
    user site, so nothing here imports its code or hands it a secret."""
    validator = _procedure_validator()
    if validator is None:
        return []
    procedure = project_path / ".agents" / "procedures" / f"{name}.md"
    rel = f".agents/procedures/{name}.md"
    try:
        run = subprocess.run([sys.executable, "-E", "-s", str(validator), str(procedure)], capture_output=True,
                             text=True, timeout=PROCEDURE_TIMEOUT, env={}, cwd=str(project_path))
    except subprocess.TimeoutExpired:
        return [Finding(project, "docs/process.md", "process-procedure-invalid",
                        f"{rel}: the procedure validator timed out after {PROCEDURE_TIMEOUT}s")]
    except OSError as exc:
        return [Finding(project, "docs/process.md", "process-procedure-invalid", f"{rel}: the procedure validator could not run: {exc}")]
    if run.returncode == 0:
        return []
    detail = (run.stderr or run.stdout).strip().splitlines()
    return [Finding(project, "docs/process.md", "process-procedure-invalid",
                    f"{rel} is not a valid procedure: {' '.join(detail[:3])[:300] or 'the validator refused it'}")]


def _check_process(project: str, project_path: Path, text: str) -> list[Finding]:
    """docs/process.md names the procedure the project runs. The name must be
    kebab-case; when .agents/procedures/ exists, <name>.md must be a file there.
    Its existence is checked here; its content is checked by the procedure
    skill's validator when one is installed."""
    rel = "docs/process.md"
    fm, _ = split_frontmatter(text)
    if fm is None:
        return []  # frontmatter-missing is already reported
    procedure = fm.get("procedure")
    if not _nonempty_str(procedure) or not KEBAB_RE.match(procedure.strip()):  # type: ignore[union-attr]
        return [Finding(project, rel, "process-procedure",
                        f"procedure {procedure!r} must be a non-empty kebab-case name "
                        r"(^[a-z0-9]+(-[a-z0-9]+)*$)")]
    name = procedure.strip()  # type: ignore[union-attr]
    procedures = project_path / ".agents" / "procedures"
    if procedures.is_dir() and not (procedures / f"{name}.md").is_file():
        return [Finding(project, rel, "process-procedure-missing",
                        f"procedure {name!r} has no file .agents/procedures/{name}.md")]
    if procedures.is_dir():
        return _check_procedure_content(project, project_path, name)
    return []


class _ViewScan(HTMLParser):
    """What a view's markup declares: its title, its meta tags, whether it needs anything from
    outside its own file, and its CSS (for the theme and the url()/@import checks)."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.external: list[str] = []  # what the view would load, for the finding message
        self.css: list[str] = []
        self._in_title = False
        self._in_style = False
        self._svg_depth = 0  # an <svg><title> names an icon, not the page

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "svg":
            self._svg_depth += 1
        if tag == "title" and not self._svg_depth:
            self._in_title = True
        elif tag == "style":
            self._in_style = True
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"].strip().lower()] = a.get("content", "")
        elif tag == "script":
            self.external.append("<script>")
        for attr, value in a.items():
            if attr.startswith("on"):
                self.external.append(f"<{tag} {attr}>")
            elif attr == "srcdoc":
                self.external.append(f"<{tag} srcdoc>")
            elif attr == "srcset":
                urls = [c.split()[0] for c in re.split(r",\s+", value.strip()) if c.strip()]  # a data: URI holds commas
                if not all(_view_inline(u) for u in urls):
                    self.external.append(f"<{tag} srcset={value!r}>")
            elif attr == "href" and tag == "a":
                if value.strip().lower().startswith("javascript:"):
                    self.external.append(f"<a href={value!r}>")
            elif (attr == "href" or attr in VIEW_URL_ATTRS) and not _view_inline(value):
                self.external.append(f"<{tag} {attr}={value!r}>")
        if "style" in a:
            self.css.append(a["style"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg":
            self._svg_depth = max(0, self._svg_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_style:
            self.css.append(data)


def _check_view(project: str, project_path: Path, view: Path, rel: str, text: str) -> list[Finding]:
    """docs/views/<name>.html is a rendering of docs/<name>.md in one self-contained file
    (contract.md, "Views"). Checked: a title, a viewport, a dark theme, nothing loaded from
    outside the file, and a source and updated date that tie it to its markdown doc, so a view
    that fell behind its source is flagged."""
    scan = _ViewScan()
    scan.feed(text)
    scan.close()
    out: list[Finding] = []

    def add(rule: str, message: str) -> None:
        out.append(Finding(project, rel, rule, message))

    if not scan.title.strip():
        add("view-title", "view has no non-empty <title>")
    if "viewport" not in scan.meta:
        add("view-viewport", 'view has no <meta name="viewport"> (it must fit a phone)')

    expected = f"docs/{view.stem}.md"
    source = scan.meta.get("source", "").strip()
    source_path = project_path / expected
    if source != expected:
        add("view-source", f'<meta name="source"> is {source!r}, expected {expected!r}')
    elif not source_path.is_file():
        add("view-source", f"source {expected} does not exist")

    updated = scan.meta.get("updated", "").strip()
    if not _is_iso_date(updated):
        add("view-updated", f'<meta name="updated"> is {updated!r}, expected an ISO date YYYY-MM-DD')
    elif source_path.is_file():
        source_text = _read(source_path, project, expected, out)
        fm = split_frontmatter(source_text)[0] if source_text is not None else None
        source_updated = fm.get("updated") if fm else None
        if _nonempty_str(source_updated) and source_updated != updated:
            add("view-updated", f"view is {updated}, {expected} is {source_updated}: re-render the view")

    css = VIEW_CSS_COMMENT_RE.sub("", "\n".join(scan.css))
    external = list(scan.external)
    if VIEW_CSS_IMPORT_RE.search(css):
        external.append("@import")
    external += [f"url({u})" for u in VIEW_CSS_URL_RE.findall(css) if u.strip() and not _view_inline(u)]
    if external:
        add("view-external", "view loads from outside its own file: " + ", ".join(external[:3]))

    if not VIEW_DARK_RE.search(css):
        add("view-theme", "view has no `@media (prefers-color-scheme: dark)` rule")
    return out


def _check_agents(project: str, project_path: Path) -> list[Finding]:
    agents = project_path / "AGENTS.md"
    if not agents.is_file():
        return [Finding(project, "AGENTS.md", "agents-md",
                        "root AGENTS.md is required but missing")]
    findings: list[Finding] = []
    text = _read(agents, project, "AGENTS.md", findings)
    if text is None:
        return findings
    return [
        Finding(project, "AGENTS.md", "agents-md", f"AGENTS.md does not mention {needle!r}")
        for needle in ("docs/overview.md", "docs/decisions")
        if needle not in text
    ]


# --- component pages -----------------------------------------------------------


_COMPONENTS_MODULE = None


def _components_module():
    """components.py, loaded from beside this file. Loaded only when docs/components/ exists, so a
    validator copied on its own keeps working for every repo that has no component layer."""
    global _COMPONENTS_MODULE
    if _COMPONENTS_MODULE is None:
        path = Path(__file__).resolve().with_name("components.py")
        if not path.is_file():
            raise ToolError(f"docs/components/ exists, so components.py must sit beside validate_docs.py "
                            f"(not found: {path})")
        spec = importlib.util.spec_from_file_location("project_docs_components", path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[spec.name] = module  # dataclasses resolves its annotations through sys.modules
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        _COMPONENTS_MODULE = module
    return _COMPONENTS_MODULE


def _h2_sections(body: str) -> list[tuple[str, list[str]]]:
    """The `## ` sections of a body as (title, lines), ignoring headings inside code fences."""
    sections: list[tuple[str, list[str]]] = []
    fence: tuple[str, int] | None = None
    for line in body.splitlines():
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
            elif (h := H2_RE.match(line)):
                sections.append((h.group(1), []))
                continue
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not m.group(2).strip():
            fence = None
        if sections:
            sections[-1][1].append(line)
    return sections


def _api_rows(lines: list[str]) -> list[str]:
    """First cell of each body row of the first table in a section (header and separator skipped)."""
    table = [ln.strip() for ln in lines if ln.strip().startswith("|")]
    return [row.lstrip("|").split("|", 1)[0].strip() for row in table[2:]]


def _api_identifiers(cell: str) -> list[str]:
    """Identifiers named by the code spans of a Public API cell: `T::{a, b}` gives T, a, b."""
    return [tok for span in CODE_SPAN_RE.findall(cell) for tok in API_TOKEN_SPLIT_RE.split(span) if tok]


def _check_component_page(project: str, rel: str, text: str) -> tuple[list[Finding], dict | None]:
    out: list[Finding] = []

    def add(rule: str, message: str) -> None:
        out.append(Finding(project, rel, rule, message))

    lines = len(text.splitlines())
    if lines > COMPONENT_MAX_LINES:
        add("component-size", f"page is {lines} lines, the limit is {COMPONENT_MAX_LINES}")
    size = len(text.encode("utf-8"))
    if size > COMPONENT_MAX_BYTES:
        add("component-size", f"page is {size} bytes, the limit is {COMPONENT_MAX_BYTES}")

    fm, body = split_frontmatter(text)
    if fm is None:
        add("component-frontmatter", "missing YAML frontmatter block (--- ... ---)")
    else:
        for key in COMPONENT_KEYS:
            if not _key_satisfied(fm, key):
                add("component-frontmatter",
                    f"missing or empty required frontmatter key: {key[0] if isinstance(key, tuple) else key}")
        if fm.get("kind") is not None and fm.get("kind") != "component":
            add("component-frontmatter", f"kind is {fm['kind']!r}, expected 'component'")
        updated = fm.get("updated")
        if _nonempty_str(updated) and not _is_iso_date(updated):  # type: ignore[arg-type]
            add("component-frontmatter", f"updated {updated!r} is not an ISO date YYYY-MM-DD")
        if "depends-on" in fm and not isinstance(fm["depends-on"], list):
            add("component-frontmatter", "depends-on must be a list such as [a, b], or [] for none")

    sections = _h2_sections(body)
    titles = [t for t, _ in sections]
    for name in COMPONENT_SECTIONS:
        if name not in titles:
            add("component-sections", f"missing section '## {name}'")
    if all(n in titles for n in COMPONENT_SECTIONS):
        present = [t for t in titles if t in COMPONENT_SECTIONS]
        if present != list(COMPONENT_SECTIONS):
            add("component-sections", f"sections are {present}, expected {list(COMPONENT_SECTIONS)} in order")

    if not _has_mermaid_block(text):
        add("component-mermaid", "page has no ```mermaid block with a body (the Flow diagram)")

    api = next((ln for t, ln in sections if t == "Public API"), [])
    if len(_api_rows(api)) > COMPONENT_API_MAX_ROWS:
        add("component-size", f"Public API has {len(_api_rows(api))} rows, the limit is {COMPONENT_API_MAX_ROWS}")
    return out, fm


def _read_tree(root: Path, cache: dict[str, str], skip: Path) -> str:
    """All text under root, joined; read once per directory. docs/ of the project is skipped, so a
    page cannot satisfy its own identifiers."""
    key = str(root)
    if key not in cache:
        chunks: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in COMPONENT_SCAN_SKIP and not (here / d == skip))
            for name in sorted(filenames):
                try:
                    chunks.append((here / name).read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    continue
        cache[key] = "\n".join(chunks)
    return cache[key]


COMPONENT_SCAN_SKIP = frozenset({".git", "node_modules", "target", "__pycache__", ".direnv", "result"})


def _check_adoption(project: str, project_path: Path) -> list[Finding]:
    """`components-not-adopted`: two or more components and no docs/components/. Quiet when the
    resolver is not beside this file, the workspace cannot be read, or the policy opts out."""
    if not Path(__file__).resolve().with_name("components.py").is_file():
        return []
    mod = _components_module()
    try:
        if not mod.policy_adopt(project_path):
            return []
        resolved = mod.resolve(project_path)
    except (mod.NeedsInput, mod.ManifestError):
        return []
    if len(resolved) < 2:
        return []
    names = ", ".join(c.name for c in resolved)
    return [Finding(project, "docs/components", "components-not-adopted",
                    f"{len(resolved)} components ({names}) and no docs/components/; add one page per component "
                    "or set docs.components.adopt: false in .agents/policy.md")]


def _check_components(project: str, project_path: Path, pages: dict[str, str]) -> list[Finding]:
    out: list[Finding] = []
    parsed: dict[str, dict | None] = {}
    for rel, text in pages.items():
        found, parsed[rel] = _check_component_page(project, rel, text)
        out += found

    mod = _components_module()
    try:
        resolved = mod.resolve(project_path)
    except mod.NeedsInput as exc:
        reasons = "; ".join(m["reason"] for m in exc.missing)
        out.append(Finding(project, "docs/components", "components-unresolved",
                           f"cannot determine the components: {reasons}. Supply one of: {'; '.join(mod.SUPPLY)}"))
        return out
    except mod.ManifestError as exc:
        raise ToolError(str(exc)) from exc

    scan_cache: dict[str, str] = {}
    for rel, fm in parsed.items():
        if fm is None or not _nonempty_str(fm.get("component")):
            continue
        cname, cpath = str(fm["component"]).strip(), str(fm.get("path", "")).strip().strip("/") or "."
        match = next((c for c in resolved if c.name == cname and c.path == cpath), None)
        if match is None:
            out.append(Finding(project, rel, "component-unknown",
                               f"component {cname!r} at path {cpath!r} matches no resolved component"))
            continue
        actual = fm.get("depends-on")
        if match.source == "manifest" and isinstance(actual, list) and actual != list(match.depends_on):
            out.append(Finding(project, rel, "component-deps",
                               f"depends-on is [{', '.join(actual)}], the manifest says "
                               f"[{', '.join(match.depends_on)}]"))
        api = next((ln for t, ln in _h2_sections(split_frontmatter(pages[rel])[1]) if t == "Public API"), [])
        wanted = dict.fromkeys(tok for cell in _api_rows(api) for tok in _api_identifiers(cell))
        if wanted:
            source = _read_tree(project_path / match.path, scan_cache, project_path / "docs")
            for tok in wanted:
                if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(tok) + r"(?![A-Za-z0-9_])", source):
                    out.append(Finding(project, rel, "component-api-unknown",
                                       f"Public API names {tok!r}, which occurs in no file under {match.path}"))

    if len(resolved) != 1:  # a single component is covered by the project layer
        for c in resolved:
            stem = mod.page_name(c.name)
            if not (project_path / "docs" / "components" / f"{stem}.md").is_file():
                out.append(Finding(project, f"docs/components/{stem}.md", "component-missing",
                                   f"component {c.name!r} ({c.path}) has no page; add one or list it under "
                                   "docs.components.exclude"))
    return out


# --- project discovery -------------------------------------------------------


def find_projects(root: Path) -> list[Path]:
    """Every dir at or under root that holds a docs/ dir OR a .git entry, including
    projects nested under a documented portfolio root (which has its own docs/ but
    must not hide its subprojects).

    A git repo below the root is a hard boundary: it is recorded, but its contents
    are not descended into, so a repo's vendored deps, submodules, or monorepo
    internals are left to that repo's own gate instead of being discovered here.
    The root itself is always descended (so a non-repo portfolio root reaches its
    repo children, and a monorepo root reaches its packages). docs/ subtrees and
    the junk dirs are pruned so docs/decisions is never mistaken for a project."""
    root = Path(root)
    projects: list[Path] = []
    skip = {"node_modules", ".direnv", "target", "result", "__pycache__", "docs"}
    for dirpath, dirnames, _ in os.walk(root):
        d = Path(dirpath)
        if (d / "docs").is_dir() or (d / ".git").exists():
            projects.append(d)
        if (d / ".git").exists() and d != root:
            dirnames[:] = []  # a nested git repo owns its subtree; do not descend
        else:
            dirnames[:] = [n for n in dirnames if n not in skip and not n.startswith(".")]
    return sorted(projects)


# --- CLI ---------------------------------------------------------------------


def _format_line(f: Finding) -> str:
    where = f"{f.project}/{f.file}" if f.file else f.project
    return f"{where}: {f.message}"


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # exit 1 must always mean findings
        print(f"error: unexpected failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _run(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description="Validate project docs against the contract.")
    parser.add_argument("path", nargs="?", default=".",
                        help="project path (default: current directory), or root path with --all")
    parser.add_argument("--all", action="store_true",
                        help="treat path as a root and validate every project under it")
    parser.add_argument("--json", action="store_true", help="machine-readable findings")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"error: path does not exist: {root}", file=sys.stderr)
        return 2

    projects = find_projects(root) if args.all else [root]
    if not projects:
        print(f"error: no projects found under {root}", file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    per_project: list[tuple[str, int]] = []
    for project_path in projects:
        if args.all and project_path != root:
            label = project_path.relative_to(root).as_posix()
        else:
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
