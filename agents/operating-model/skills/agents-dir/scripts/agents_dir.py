#!/usr/bin/env python3
"""Validate a project's `.agents/` directory against the layout contract. Stdlib only.

    agents_dir.py REPO [--base REF]

Without `--base` it checks the files as they are. With `--base` it also checks the change since that
ref: a change to a process document must add an iteration record that covers it.

The process is defined by documents in the project's own git repo, each answering one question:
`policy.md` (settings), `procedures/<name>.md` (structure), `charter.md` (who the owner is, where
they are reached, which procedure runs on which trigger), `iterations/NNNN-<slug>.md` (what changed
and what it did) and `runs/` (runtime output: git-ignored, never a source). Names this tool does not
own are left alone, so other tools can keep files in `.agents/`.
"""
import argparse
import os
import re
import subprocess
import sys

_SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(_SKILLS, "procedure", "scripts"))
from validate_procedure import parse_frontmatter, validate_text  # noqa: E402

__all__ = ("check_agents_dir", "process_revision", "main")

AGENTS = ".agents"
PROCESS_DOCS = (".agents/policy.md", ".agents/charter.md")  # plus .agents/procedures/*.md
ITERATION = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
OUTCOMES = ("initial", "pending", "confirmed", "regressed", "rolled-back", "kept", "superseded")
WINDOW = re.compile(r"^[1-9][0-9]{0,5} (?:stages|runs)\Z")
REVISION = re.compile(r"^[0-9a-f]{7,40}\Z")
SECRET_KEYS = ("key", "secret", "token", "password")
MAX_DOC = 256 * 1024  # as the resolver: a larger process document is refused, never read


def _git(repo, *args):
    """Run git in `repo`. Returns stdout, or None when git fails or is missing."""
    # A repo's own config must not run code here: no fsmonitor, no inherited GIT_DIR or system config.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        run = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                             capture_output=True, text=True, env=env)
    except OSError:
        return None
    return run.stdout if run.returncode == 0 else None


def _read(path, rel, errs):
    """Read one process document. A symlink or an oversized file is an error and its content is never read."""
    if os.path.islink(path):
        errs.append(f"{rel}: is a symlink; a process document must be a regular file")
        return None
    try:
        if os.path.getsize(path) > MAX_DOC:
            errs.append(f"{rel}: is too large (over {MAX_DOC // 1024} KB)")
            return None
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        errs.append(f"{rel}: cannot read: {exc}")
        return None


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _markdown(directory, rel=None, errs=None):
    """The lowercase `.md` documents of a directory. With `errs`, also report what must not be there: a
    symlink, a suffix that only a case-insensitive filesystem reads as `.md`, and a subdirectory."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    keep = []
    for n in sorted(names):
        path = os.path.join(directory, n)
        if errs is not None and os.path.islink(path):
            errs.append(f"{rel}/{n}: is a symlink; a process document must be a regular file")
        elif errs is not None and n.lower().endswith(".md") and not n.endswith(".md"):
            errs.append(f"{rel}/{n}: the suffix must be lowercase .md; a case-insensitive filesystem would load it as a document")
        elif errs is not None and os.path.isdir(path):
            errs.append(f"{rel}/{n}: a directory is not allowed here")
        elif n.endswith(".md") and os.path.isfile(path) and not os.path.islink(path):
            keep.append(n)
    return keep


def _walk_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_keys(v)


def _procedures(agents, errs):
    """Validate each procedure file. Returns the names of the ones present."""
    names = []
    folder = os.path.join(agents, "procedures")
    for fname in _markdown(folder, f"{AGENTS}/procedures", errs):
        rel = f"{AGENTS}/procedures/{fname}"
        text = _read(os.path.join(folder, fname), rel, errs)
        if text is None:
            continue
        stem = fname[:-3]
        names.append(stem)
        errs.extend(f"{rel}: {e}" for e in validate_text(text, rel, strict=True))
        fm, ferrs = parse_frontmatter(text, rel)
        if not ferrs and fm.get("name") != stem:
            errs.append(f"{rel}: 'name' is '{fm.get('name')}' but the file is {fname}")
    return names


def _front(agents, fname, errs):
    """Read a top-level document. Returns (relative name, frontmatter) or None."""
    rel = f"{AGENTS}/{fname}"
    path = os.path.join(agents, fname)
    if not os.path.lexists(path):
        return None
    text = _read(path, rel, errs)
    if text is None:
        return None
    fm, ferrs = parse_frontmatter(text, rel)
    if ferrs:
        errs.extend(ferrs)
        return None
    return rel, fm


def _policy(agents, procedures, errs):
    found = _front(agents, "policy.md", errs)
    if found and "procedure" in found[1] and found[1]["procedure"] not in procedures:
        errs.append(f"{found[0]}: procedure '{found[1]['procedure']}' is not in {AGENTS}/procedures/")


def _charter(agents, procedures, errs):
    found = _front(agents, "charter.md", errs)
    if not found:
        return
    rel, fm = found
    owner = fm.get("owner")
    if not isinstance(owner, dict):
        errs.append(f"{rel}: 'owner' must be a map with 'channel' and 'answer-path'")
    else:
        errs += [f"{rel}: owner needs a non-empty '{k}'" for k in ("channel", "answer-path") if not _text(owner.get(k))]
    if "delegate" in fm and not _text(fm["delegate"]):
        errs.append(f"{rel}: 'delegate' must be the name of an entity")
    if "procedure" in fm and fm["procedure"] not in procedures:
        errs.append(f"{rel}: procedure '{fm['procedure']}' is not in {AGENTS}/procedures/")
    triggers = fm.get("triggers")
    if triggers is not None and not isinstance(triggers, dict):
        errs.append(f"{rel}: 'triggers' must be a map of trigger name to procedure name")
    elif isinstance(triggers, dict):
        errs += [f"{rel}: trigger '{t}' names procedure '{p}', which does not exist" for t, p in triggers.items() if p not in procedures]
    errs += [f"{rel}: '{k}' looks like a secret: a charter holds none" for k in _walk_keys(fm) if k.lower() in SECRET_KEYS]


def _iteration_errors(rel, fm):
    errs = []
    change = fm.get("change")
    if not isinstance(change, dict):
        errs.append(f"{rel}: needs a 'change' map")
    else:
        if not _text(change.get("reason")):
            errs.append(f"{rel}: change needs a 'reason'")
        metrics = change.get("metrics")
        if not isinstance(metrics, list) or not metrics or not all(_text(m) for m in metrics):
            errs.append(f"{rel}: change 'metrics' must be a non-empty list of names")
        if change.get("direction") not in ("up", "down"):
            errs.append(f"{rel}: change 'direction' must be 'up' or 'down'")
        if not isinstance(change.get("window"), str) or not WINDOW.match(change["window"]):
            errs.append(f"{rel}: change 'window' must look like '5 stages' or '3 runs'")
    touches = fm.get("touches")
    if not isinstance(touches, list) or not touches:
        errs.append(f"{rel}: 'touches' must list the process documents it changed")
    else:
        for t in touches:
            ok = isinstance(t, str) and (t in ("policy.md", "charter.md") or (t.startswith("procedures/") and t.endswith(".md")))
            if not ok:
                errs.append(f"{rel}: 'touches' names '{t}', which is not a process document")
    if fm.get("outcome") not in OUTCOMES:
        errs.append(f"{rel}: 'outcome' must be one of {', '.join(OUTCOMES)}")
    if "revision" in fm and not (isinstance(fm["revision"], str) and REVISION.match(fm["revision"])):
        errs.append(f"{rel}: 'revision' must be a commit id")
    return errs


def _iterations(agents, errs):
    folder = os.path.join(agents, "iterations")
    numbers = {}
    for fname in _markdown(folder, f"{AGENTS}/iterations", errs):
        rel = f"{AGENTS}/iterations/{fname}"
        match = ITERATION.match(fname)
        if not match:
            errs.append(f"{rel}: name must be NNNN-<slug>.md, such as 0001-tighten-review.md")
            continue
        numbers.setdefault(int(match.group(1)), []).append(fname)
        text = _read(os.path.join(folder, fname), rel, errs)
        if text is None:
            continue
        fm, ferrs = parse_frontmatter(text, rel)
        errs.extend(ferrs if ferrs else _iteration_errors(rel, fm))
    errs += [f"iteration number {n:04d} is used by {', '.join(sorted(names))}" for n, names in sorted(numbers.items()) if len(names) > 1]
    if numbers:
        errs += [f"iteration number {n:04d} is missing: numbers must be contiguous" for n in range(1, max(numbers) + 1) if n not in numbers]


def _runs_ignored(repo, errs):
    if _git(repo, "rev-parse", "--git-dir") is None:
        return  # not a git repo: nothing to ignore
    if _git(repo, "check-ignore", "-q", f"{AGENTS}/runs/probe") is None:
        errs.append(f"{AGENTS}/runs/ must be git-ignored: it holds run output, never a source")


def _covered(repo, added):
    """The process documents that the iteration records added in this change say they touch."""
    covered = set()
    for rel in added:
        text = _read(os.path.join(repo, rel), rel, [])  # a symlink or a huge file covers nothing
        if text is None:
            continue
        fm, ferrs = parse_frontmatter(text, rel)
        touches = fm.get("touches") if not ferrs else None
        if isinstance(touches, list):
            covered.update(f"{AGENTS}/{t}" for t in touches if isinstance(t, str))
    return covered


def _changed_since(repo, base, errs):
    """The change rule: a process document changes only together with an iteration record."""
    if _git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}") is None:
        errs.append(f"base ref '{base}' was not found")
        return
    diff = _git(repo, "diff", "--name-status", "-M", f"{base}...HEAD", "--", AGENTS)
    if diff is None:
        errs.append(f"could not diff against base '{base}'")
        return
    process, added = set(), []
    for line in diff.splitlines():
        status, *paths = line.split("\t")
        for path in paths:
            if path in PROCESS_DOCS or (path.startswith(f"{AGENTS}/procedures/") and path.lower().endswith(".md")):
                process.add(path)
        old = paths[0]
        match = ITERATION.match(os.path.basename(old)) if old.startswith(f"{AGENTS}/iterations/") else None
        if match and status[0] in "DR":
            errs.append(f"iteration record {match.group(1)} may not be deleted or renamed")
        if status[0] == "A" and old.startswith(f"{AGENTS}/iterations/"):
            if os.path.dirname(old) == f"{AGENTS}/iterations" and ITERATION.match(os.path.basename(old)):
                added.append(old)
            else:
                errs.append(f"{old}: not a valid iteration record; name it {AGENTS}/iterations/NNNN-<slug>.md")
    if process and not added:
        errs.append(f"{', '.join(sorted(process))} changed with no new iteration record in {AGENTS}/iterations/")
    elif process:
        covered = _covered(repo, added)
        for path in sorted(process - covered):
            errs.append(f"{path} changed but is not covered by the 'touches' of any new iteration record")


def check_agents_dir(repo, base=None):
    """Return a list of error strings for the `.agents/` directory of `repo`."""
    if not os.path.isdir(repo):
        return [f"{repo} is not a directory"]
    agents = os.path.join(repo, AGENTS)
    errs = []
    if os.path.isdir(agents):
        procedures = _procedures(agents, errs)
        _policy(agents, procedures, errs)
        _charter(agents, procedures, errs)
        _iterations(agents, errs)
        _runs_ignored(repo, errs)
    if base is not None:
        _changed_since(repo, base, errs)
    return errs


def process_revision(repo):
    """The commit that last changed a process document, or None. A snapshot pins this revision."""
    out = _git(repo, "log", "-1", "--format=%H", "--", *PROCESS_DOCS, f"{AGENTS}/procedures")
    return (out.strip() or None) if out is not None else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("repo")
    ap.add_argument("--base", help="also check the change since this ref")
    a = ap.parse_args(argv)
    errs = check_agents_dir(a.repo, a.base)
    for e in errs:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
