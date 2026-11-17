#!/usr/bin/env python3
"""Resolve a run's process documents from the project and the user's config. Stdlib only.

    resolver.py PROJECT [--procedure NAME] [--allow-dirty]

For each document the project's `.agents/` wins over the user's `$XDG_CONFIG_HOME/agents/` (default
`~/.config/agents/`). With neither, there is nothing to resolve and the tool does nothing.

"Project wins" lets a cloned repo override a trusted user setup, so the override is guarded: a policy
key the user locked, a project procedure that weakens the user's floor or protected set, and a
charter that redirects the user's owner are all errors. A run also needs every policy key its
procedure declares, and refuses process documents with uncommitted changes.
"""
import argparse
import hashlib
import json
import math
import os
import re
import secrets
import sys

from agents_dir import AGENTS, PROCESS_DOCS, _git, process_revision
from runtime import CAPS, COLLECTORS, new_state
from validate_procedure import (bindings_for, check_bindings, override_violations, parse_frontmatter, parse_procedure,
                                policy_get, validate_text)
from policy_loader import PolicyError, resolve as resolve_policy

__all__ = ("resolve", "start_run", "ResolutionError", "main")

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\Z")
MAX_DOC = 256 * 1024
MISSING = object()


class ResolutionError(Exception):
    """The documents cannot start a run. `errors` lists why."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _user_dir(environ):
    xdg = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME") or os.path.expanduser("~"), ".config")
    return os.path.join(xdg, "agents")


def _names(directory):
    """The safe procedure names in a `procedures/` directory."""
    try:
        files = os.listdir(os.path.join(directory, "procedures"))
    except OSError:
        return []
    return sorted(f[:-3] for f in files if f.endswith(".md") and NAME.match(f[:-3]))


def _has_documents(directory):
    return bool(_names(directory)) or any(os.path.lexists(os.path.join(directory, f)) for f in ("policy.md", "charter.md"))


def _read(path, label, errs):
    """Read one process document. A symlink, a huge file or unreadable bytes is an error, never a crash."""
    if os.path.islink(path):
        errs.append(f"{label}: is a symlink; a process document must be a regular file")
        return None
    try:
        if os.path.getsize(path) > MAX_DOC:
            errs.append(f"{label}: is too large (over {MAX_DOC // 1024} KB)")
            return None
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        errs.append(f"{label}: cannot read: {type(exc).__name__}")
        return None


def _front(path, label, errs):
    """A document's frontmatter map, or None. Absent is not an error."""
    if not os.path.lexists(path):
        return None
    text = _read(path, label, errs)
    if text is None:
        return None
    fm, ferrs = parse_frontmatter(text, label)
    errs.extend(ferrs)
    return fm


def _pick(name_arg, policy, charters):
    """The procedure to run: an explicit name, then the policy, then the charter."""
    for source in (name_arg, policy.get("procedure"), *(c.get("procedure") for c in charters if c)):
        if source is not None:
            return source
    return None


def _locked(user_policy, project_policy, errs):
    """A project may not change a key the user's policy locked."""
    for key in (user_policy or {}).get("locked") or []:
        if not isinstance(key, str):
            continue
        mine = policy_get(project_policy or {}, key, default=MISSING)
        theirs = policy_get(user_policy, key, default=MISSING)
        if mine is not MISSING and theirs is not MISSING and mine != theirs:
            errs.append(f"project policy sets '{key}' to {mine!r}, but the user's policy locked it to {theirs!r}")


def _revision(project, project_docs, user_docs, allow_dirty, errs):
    rev = {"project": None, "user": None, "dirty": False}
    if project_docs and _git(project, "rev-parse", "--git-dir") is not None:
        rev["project"] = process_revision(project)
        status = _git(project, "status", "--porcelain", "--", *PROCESS_DOCS, f"{AGENTS}/procedures")
        changed = [line[3:] for line in (status or "").splitlines()]
        rev["dirty"] = bool(changed)
        if changed and not allow_dirty:
            errs.append(f"process documents have uncommitted changes ({', '.join(changed)}): commit them or allow a dirty tree")
    if user_docs:
        digest = hashlib.sha256(json.dumps(sorted(user_docs.items())).encode()).hexdigest()
        rev["user"] = digest[:16]
    return rev


def resolve(project, *, environ=None, name=None, allow_dirty=False):
    """Resolve the process documents for a project. Returns None when there are none to resolve.

    Otherwise a dict: `procedure`, `procedure_text`, `policy` (resolved), `bindings`, `charter`,
    `revision` (`project` commit, `user` hash, `dirty`), `sources` and `errors`. A run may start only
    when `errors` is empty and `procedure` is set."""
    environ = os.environ if environ is None else environ
    mine, theirs = os.path.join(project, AGENTS), _user_dir(environ)
    if not (_has_documents(mine) or _has_documents(theirs)):
        return None
    errs, used_user = [], {}
    out = {"procedure": None, "procedure_text": None, "policy": {}, "bindings": {}, "charter": None,
           "revision": None, "sources": {"policy": [], "procedure": None, "charter": None}, "errors": errs}

    # policy: layered per key, the project over the user
    user_policy = _front(os.path.join(theirs, "policy.md"), "<user>/policy.md", errs)
    proj_policy = _front(os.path.join(mine, "policy.md"), f"{AGENTS}/policy.md", errs)
    out["sources"]["policy"] = [s for s, d in (("user", user_policy), ("project", proj_policy)) if d is not None]
    if user_policy is not None:
        used_user["policy.md"] = _read(os.path.join(theirs, "policy.md"), "<user>/policy.md", [])
    _locked(user_policy, proj_policy, errs)
    if not errs:
        try:
            out["policy"] = resolve_policy(project, global_path=os.path.join(theirs, "policy.md"))
        except PolicyError as exc:
            errs.append(str(exc))
    policy = out["policy"]

    # charter: the project over the user, but never a different owner
    user_charter = _front(os.path.join(theirs, "charter.md"), "<user>/charter.md", errs)
    proj_charter = _front(os.path.join(mine, "charter.md"), f"{AGENTS}/charter.md", errs)
    if user_charter and proj_charter and isinstance(user_charter.get("owner"), dict):
        if proj_charter.get("owner") != user_charter["owner"]:
            errs.append(f"{AGENTS}/charter.md names a different owner than the user's charter: a project cannot redirect where the owner is reached")
    out["charter"] = proj_charter if proj_charter is not None else user_charter
    out["sources"]["charter"] = "project" if proj_charter is not None else ("user" if user_charter is not None else None)
    if out["sources"]["charter"] == "user":
        used_user["charter.md"] = _read(os.path.join(theirs, "charter.md"), "<user>/charter.md", [])

    # which procedure
    wanted = _pick(name, policy, (proj_charter, user_charter))
    available = sorted(set(_names(mine)) | set(_names(theirs)))
    if wanted is None and len(available) == 1:
        wanted = available[0]
    if wanted is None and len(available) > 1:
        errs.append(f"several procedures are available ({', '.join(available)}) and none is named: set 'procedure' in the policy")
    elif wanted is not None and not (isinstance(wanted, str) and NAME.match(wanted)):
        errs.append(f"procedure name {wanted!r} is not a safe name: lowercase letters, digits and dashes")
    elif wanted is not None:
        _procedure(out, wanted, mine, theirs, used_user, errs)

    out["revision"] = _revision(project, _has_documents(mine), used_user, allow_dirty, errs)
    return out


def _procedure(out, name, mine, theirs, used_user, errs):
    paths = {s: os.path.join(d, "procedures", f"{name}.md") for s, d in (("project", mine), ("user", theirs))}
    source = next((s for s in ("project", "user") if os.path.lexists(paths[s])), None)
    if source is None:
        errs.append(f"procedure '{name}' is in neither {AGENTS}/procedures/ nor the user's procedures/")
        return
    label = f"{AGENTS}/procedures/{name}.md" if source == "project" else f"<user>/procedures/{name}.md"
    text = _read(paths[source], label, errs)
    if text is None:
        return
    out.update(procedure=name, procedure_text=text)
    out["sources"]["procedure"] = source
    if source == "user":
        used_user[f"procedures/{name}.md"] = text
    errs.extend(f"{label}: {e}" for e in validate_text(text, label, strict=True))
    proc, perrs = parse_procedure(text, label)
    if perrs or proc is None:
        return
    fm, _ = parse_frontmatter(text, label)
    if fm.get("name") != name:
        errs.append(f"{label}: 'name' is '{fm.get('name')}' but the file is {name}.md")
    if source == "project" and os.path.lexists(paths["user"]):
        user_text = _read(paths["user"], f"<user>/procedures/{name}.md", errs)
        user_proc = parse_procedure(user_text, "<user>")[0] if user_text else None
        if user_proc:
            errs.extend(f"project procedure '{name}' weakens the user's: {v}" for v in override_violations(user_proc, proc))
    errs.extend(check_bindings(proc, out["policy"], name))
    out["bindings"] = bindings_for(proc, out["policy"])


def _runtime_policy(policy):
    """The policy values the runtime checks, as the numbers and lists it needs. A file holds text."""
    out, errs = {}, []
    for key in CAPS:
        if key in policy:
            raw = policy[key]
            if isinstance(raw, str) and raw.isdecimal():
                out[key] = int(raw)
            else:
                errs.append(f"policy '{key}' must be a non-negative whole number, not {raw!r}")
    if "regression-threshold" in policy:
        raw = policy["regression-threshold"]
        try:
            value = float(raw) if isinstance(raw, str) else None
        except ValueError:
            value = None
        if value is None or not math.isfinite(value) or value < 0:
            errs.append(f"policy 'regression-threshold' must be a non-negative number, not {raw!r}")
        else:
            out["regression-threshold"] = value
    if "safety-metrics" in policy:
        raw = policy["safety-metrics"]
        unknown = [m for m in raw if m not in COLLECTORS] if isinstance(raw, list) else None
        if unknown is None or unknown:
            errs.append(f"policy 'safety-metrics' must list metrics the runtime observes, not {raw!r}")
        else:
            out["safety-metrics"] = list(raw)
    return out, errs


def start_run(project, *, environ=None, name=None, allow_dirty=False, trust="claims", run_id=None):
    """Freeze the resolved documents into a run. Returns None when there is nothing to run.

    Raises ResolutionError when the documents cannot start one."""
    got = resolve(project, environ=environ, name=name, allow_dirty=allow_dirty)
    if got is None or (got["procedure"] is None and not got["errors"]):
        return None
    if got["errors"]:
        raise ResolutionError(got["errors"])
    policy, errs = _runtime_policy(got["policy"])
    if errs:
        raise ResolutionError(errs)
    try:
        state = new_state(got["procedure_text"], policy=policy, bindings=got["bindings"], revision=got["revision"],
                          trust=trust, run_id=run_id or secrets.token_hex(8))
    except ValueError as exc:
        raise ResolutionError([str(exc)]) from exc
    state["resolution"] = {"procedure": got["procedure"], "sources": got["sources"]}
    return state


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--procedure", help="run this procedure, overriding the policy")
    ap.add_argument("--allow-dirty", action="store_true", help="accept uncommitted process documents")
    a = ap.parse_args(argv)
    got = resolve(a.project, name=a.procedure, allow_dirty=a.allow_dirty)
    if got is None:
        print("no process documents found: nothing to do")
        return 0
    for e in got["errors"]:
        print(f"ERROR: {e}", file=sys.stderr)
    summary = {k: got[k] for k in ("procedure", "revision", "sources", "bindings", "errors")}
    if not got["errors"]:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if got["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
