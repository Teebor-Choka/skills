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
import tempfile

from agents_dir import AGENTS, PROCESS_DOCS, _git, process_revision
from runtime import CAPS, COLLECTORS, new_state
from validate_procedure import (POLICY_KEY, bindings_for, check_bindings, override_violations, parse_frontmatter,
                                parse_procedure, validate_text)
from policy_loader import PolicyError, _overlay, resolve as resolve_policy

__all__ = ("resolve", "start_run", "ResolutionError", "main")

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\Z")
MAX_DOC = 256 * 1024
MAX_INLINE_PROCEDURES = 64
MAX_INLINE_FILE = 8 * MAX_DOC
MISSING = object()
WHOLE = re.compile(r"[0-9]{1,9}\Z")  # a count; longer or non-ASCII digits are not a sane limit


class ResolutionError(Exception):
    """The documents cannot start a run. `errors` lists why."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _inline_docs(inline, errs):
    """The documents a parent passes in: `policy`, `charter` (text) and `procedures` (name to text)."""
    if not isinstance(inline, dict):
        errs.append("inline documents must be a map of policy, charter and procedures")
        return {}
    for key in inline:
        if key not in ("policy", "charter", "procedures"):
            errs.append(f"inline documents: unknown key '{key}' (allowed: policy, charter, procedures)")
    procs = inline.get("procedures", {})
    if not isinstance(procs, dict):
        errs.append("inline procedures must be a map of name to text")
        procs = {}
    texts = {k: inline[k] for k in ("policy", "charter") if k in inline}
    texts.update({f"procedures/{n}": t for n, t in procs.items()})
    if len(procs) > MAX_INLINE_PROCEDURES:
        errs.append(f"inline procedures: at most {MAX_INLINE_PROCEDURES} allowed, got {len(procs)}")
    for key, text in texts.items():
        try:
            fits = isinstance(text, str) and len(text.encode("utf-8")) <= MAX_DOC
        except UnicodeEncodeError:  # JSON allows a lone surrogate; it is not text
            fits = False
        if not fits:
            errs.append(f"inline {key} must be valid text of at most {MAX_DOC // 1024} KB")
    for n in procs:
        if not (isinstance(n, str) and NAME.match(n)):
            errs.append(f"inline procedure name {n!r} is not a safe name: lowercase letters, digits and dashes")
    return {} if errs else {"policy": inline.get("policy"), "charter": inline.get("charter"), "procedures": dict(procs)}


def _inline_front(text, label, errs):
    if text is None:
        return None
    fm, ferrs = parse_frontmatter(text, label)
    errs.extend(ferrs)
    return fm


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


def _read(path, label, errs, follow=False):
    """Read one process document. A symlink (unless `follow`: the user's own layer), a huge file or
    unreadable bytes is an error, never a crash."""
    if not follow and os.path.islink(path):
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


def _front(path, label, errs, follow=False):
    """A document's frontmatter map, or None. Absent is not an error."""
    if not os.path.lexists(path):
        return None
    text = _read(path, label, errs, follow)
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


def _dig(policy, key):
    """The value at a dotted path through nested maps, or MISSING."""
    for part in key.split("."):
        if not isinstance(policy, dict) or part not in policy:
            return MISSING
        policy = policy[part]
    return policy


def _shadows(policy, key):
    """Where a policy sets the head of `key` for one skill (`<skill>: {key: ..}`) or one file (`files:`)."""
    head, out = key.split(".")[0], {}
    files = policy.get("files")
    for glob, over in (files.items() if isinstance(files, dict) else ()):
        if isinstance(over, dict) and head in over:
            out[("files", glob)] = over[head]
    for name, section in policy.items():
        if name not in ("files", head) and not name.startswith("_") and isinstance(section, dict) and head in section:
            out[("skill", name)] = section[head]
    return out


def _locked(user_policy, user_path, resolved, project, errs):
    """A resolved policy must hold, for every key the user locked, what the user's layer alone gives.

    Compared on the result, so a missing key, a scalar over a map and a sibling overlay that
    replaces a nested map all count as overrides."""
    keys = (user_policy or {}).get("locked")
    if keys is None:
        return
    if not (isinstance(keys, list) and keys and all(isinstance(k, str) and POLICY_KEY.match(k) for k in keys)):
        errs.append(f"user policy 'locked' must be a list of dotted policy keys, not {keys!r}")
        return
    with tempfile.TemporaryDirectory() as empty:
        alone = resolve_policy(empty, global_path=user_path)
    for key in keys:
        want, got = _dig(alone, key), _dig(resolved, key)
        if got != want:
            errs.append(f"project policy changes '{key}' to {got!r}, but the user's policy locked it to {want!r}")
        if _shadows(alone, key) != _shadows(resolved, key):
            errs.append(f"project policy overrides locked key '{key}' for a skill or a file, which the user's policy locked")


def _changed(project):
    """The process documents that differ from HEAD, compared as raw bytes, or None when git cannot say.

    Not `git status`: that re-hashes files through the repo's own filters and skips ignored ones. Here a
    tracked file is hashed with no filter, and a file git does not track counts as changed."""
    tree = _git(project, "ls-tree", "-r", "-z", "HEAD", "--", *PROCESS_DOCS, f"{AGENTS}/procedures")
    if tree is None:
        return None
    tracked = {}
    for record in filter(None, tree.split("\0")):
        meta, _, path = record.partition("\t")
        tracked[path] = meta.split()[2]
    on_disk = [p for p in PROCESS_DOCS if os.path.lexists(os.path.join(project, p))]
    folder = os.path.join(project, AGENTS, "procedures")
    if os.path.isdir(folder):
        on_disk += [f"{AGENTS}/procedures/{f}" for f in sorted(os.listdir(folder)) if not os.path.isdir(os.path.join(folder, f))]
    changed = []
    for path in sorted(set(tracked) | set(on_disk)):
        if path not in on_disk or path not in tracked:
            changed.append(path)
            continue
        digest = _git(project, "hash-object", "--no-filters", "--", path)
        if digest is None or digest.strip() != tracked[path]:
            changed.append(path)
    return changed


def _revision(project, project_docs, user_docs, allow_dirty, errs):
    rev = {"project": None, "user": None, "dirty": False}
    if project_docs and _git(project, "rev-parse", "--git-dir") is not None:
        rev["project"] = process_revision(project)
        changed = _changed(project)
        if changed is None:
            errs.append("git could not report the state of the process documents: the revision cannot be pinned")
            return rev
        rev["dirty"] = bool(changed)
        if changed and not allow_dirty:
            errs.append(f"process documents have uncommitted changes ({', '.join(changed)}): commit them or allow a dirty tree")
    if user_docs:
        digest = hashlib.sha256(json.dumps(sorted(user_docs.items())).encode()).hexdigest()
        rev["user"] = digest[:16]
    return rev


def resolve(project, *, environ=None, name=None, allow_dirty=False, inline=None):
    """Resolve the process documents for a project. Returns None when there are none to resolve.

    Otherwise a dict: `procedure`, `procedure_text`, `policy` (resolved), `bindings`, `charter`,
    `revision` (`project` commit, `user` and `inline` hashes, `dirty`), `sources` and `errors`. A run
    may start only when `errors` is empty and `procedure` is set.

    `inline` is a parent's `policy`, `charter` and `procedures`, passed directly: the highest layer,
    guarded exactly like the project's."""
    environ = os.environ if environ is None else environ
    mine, theirs = os.path.join(project, AGENTS), _user_dir(environ)
    if not (_has_documents(mine) or _has_documents(theirs) or inline):
        return None
    errs, used_user = [], {}
    linked = [rel for rel in (AGENTS, f"{AGENTS}/procedures") if os.path.islink(os.path.join(project, rel))]
    out = {"procedure": None, "procedure_text": None, "policy": {}, "bindings": {}, "charter": None,
           "revision": None, "sources": {"policy": [], "procedure": None, "charter": None}, "errors": errs}

    if linked:
        errs.extend(f"{rel} is a symlink; process documents must live in the project" for rel in linked)
        return out
    inl = _inline_docs(inline, errs) if inline else {"policy": None, "charter": None, "procedures": {}}
    if errs:
        return out

    # policy: layered per key, the project over the user
    user_policy = _front(os.path.join(theirs, "policy.md"), "<user>/policy.md", errs, follow=True)
    proj_policy = _front(os.path.join(mine, "policy.md"), f"{AGENTS}/policy.md", errs)
    inl_policy = _inline_front(inl["policy"], "<inline>/policy", errs)
    out["sources"]["policy"] = [s for s, d in (("user", user_policy), ("project", proj_policy), ("inline", inl_policy)) if d is not None]
    if user_policy is not None:
        used_user["policy.md"] = _read(os.path.join(theirs, "policy.md"), "<user>/policy.md", [], follow=True)
    if not errs:
        try:
            out["policy"] = resolve_policy(project, global_path=os.path.join(theirs, "policy.md"))
            if inl_policy:
                _overlay(out["policy"], inl_policy, out["policy"].setdefault("_provenance", {}), "inline")
            _locked(user_policy, os.path.join(theirs, "policy.md"), out["policy"], project, errs)
        except PolicyError as exc:
            errs.append(str(exc))
    policy = out["policy"]

    # charter: the project over the user, but never a different owner
    user_charter = _front(os.path.join(theirs, "charter.md"), "<user>/charter.md", errs, follow=True)
    proj_charter = _front(os.path.join(mine, "charter.md"), f"{AGENTS}/charter.md", errs)
    inl_charter = _inline_front(inl["charter"], "<inline>/charter", errs)
    if user_charter is not None and "owner" in user_charter and not isinstance(user_charter["owner"], dict):
        errs.append("<user>/charter.md: 'owner' must be a map with 'channel' and 'answer-path'")
    for label, charter, lowers in ((f"{AGENTS}/charter.md", proj_charter, (user_charter,)),
                                   ("<inline>/charter", inl_charter, (user_charter, proj_charter))):
        for lower in lowers:
            if charter is not None and lower is not None and isinstance(lower.get("owner"), dict) and charter.get("owner") != lower["owner"]:
                errs.append(f"{label} names a different owner than a lower charter: only the owner can redirect where they are reached")
    layers = (("inline", inl_charter), ("project", proj_charter), ("user", user_charter))
    top = next(((src, c) for src, c in layers if c is not None), (None, None))
    out["charter"], out["sources"]["charter"] = top[1], top[0]
    if out["sources"]["charter"] == "user":
        used_user["charter.md"] = _read(os.path.join(theirs, "charter.md"), "<user>/charter.md", [], follow=True)

    # which procedure
    wanted = _pick(name, policy, (inl_charter, proj_charter, user_charter))
    mine_names, their_names = _names(mine), _names(theirs)
    available = sorted(set(mine_names) | set(their_names) | set(inl["procedures"]))
    base = {"user": _pick(None, user_policy or {}, (user_charter,)), "user_names": their_names,
            "project": _pick(None, proj_policy or {}, (proj_charter,))}
    for layer, names in (("user", their_names), ("project", mine_names)):
        if base[layer] is None and len(names) == 1:
            base[layer] = names[0]
    if wanted is None and len(available) == 1:
        wanted = available[0]
    if wanted is None and len(available) > 1:
        errs.append(f"several procedures are available ({', '.join(available)}) and none is named: set 'procedure' in the policy")
    elif wanted is not None and not (isinstance(wanted, str) and NAME.match(wanted)):
        errs.append(f"procedure name {wanted!r} is not a safe name: lowercase letters, digits and dashes")
    elif wanted is not None:
        _procedure(out, wanted, mine, theirs, used_user, errs, base, inl["procedures"])

    out["revision"] = _revision(project, _has_documents(mine), used_user, allow_dirty, errs)
    if inline:
        out["revision"]["inline"] = hashlib.sha256(json.dumps(inl, sort_keys=True).encode()).hexdigest()[:16]
    return out


def _procedure(out, name, mine, theirs, used_user, errs, base=None, inline=None):
    inline = inline or {}
    paths = {s: os.path.join(d, "procedures", f"{name}.md") for s, d in (("project", mine), ("user", theirs))}
    labels = {"inline": f"<inline>/procedures/{name}.md", "project": f"{AGENTS}/procedures/{name}.md",
              "user": f"<user>/procedures/{name}.md"}
    source = "inline" if name in inline else next((s for s in ("project", "user") if os.path.lexists(paths[s])), None)
    if source is None:
        errs.append(f"procedure '{name}' is in neither {AGENTS}/procedures/ nor the user's procedures/")
        return
    label = labels[source]
    text = inline[name] if source == "inline" else _read(paths[source], label, errs, follow=source == "user")
    if text is None:
        return
    out.update(procedure=name, procedure_text=text)
    out["sources"]["procedure"] = source
    if source == "user":
        used_user[f"procedures/{name}.md"] = text
    invalid = validate_text(text, label, strict=True)
    errs.extend(f"{label}: {e}" for e in invalid)
    proc, perrs = parse_procedure(text, label)
    if invalid or perrs or proc is None:
        return  # a procedure that is not valid is never compared: the guards assume a well-formed one
    fm, _ = parse_frontmatter(text, label)
    if fm.get("name") != name:
        errs.append(f"{label}: 'name' is '{fm.get('name')}' but the file is {name}.md")
    for lower_label, lower_text in _lowers(source, name, mine, theirs, base or {}, errs):
        bad = validate_text(lower_text, lower_label, strict=True)
        errs.extend(f"{lower_label}: {e}" for e in bad)
        lower = None if bad else parse_procedure(lower_text, lower_label)[0]
        if lower:
            errs.extend(f"{label} weakens {lower_label}: {v}" for v in override_violations(lower, proc))
    errs.extend(check_bindings(proc, out["policy"], name))
    out["bindings"] = bindings_for(proc, out["policy"])


def _lowers(source, name, mine, theirs, base, errs):
    """The (label, text) of each lower layer's procedure the chosen one must not weaken.

    Per layer, the one of this name and the one that layer runs: a rename, or a swap for another
    procedure of the user's, must not shed a floor. Inline answers to the project too."""
    wanted = []
    if source == "inline":
        wanted += [("project", name), ("project", base.get("project"))]
    if source != "user":
        wanted += [("user", name), ("user", base.get("user"))]
    found, seen = [], set()
    for layer, n in wanted:
        if (layer, n) in seen or not (isinstance(n, str) and NAME.match(n)):
            continue
        seen.add((layer, n))
        user = layer == "user"
        path = os.path.join(theirs if user else mine, "procedures", f"{n}.md")
        label = f"<user>/procedures/{n}.md" if user else f"{AGENTS}/procedures/{n}.md"
        text = _read(path, label, errs, follow=user) if os.path.lexists(path) else None
        if text:
            found.append((label, text))
    names = base.get("user_names") or []
    if source != "user" and len(names) > 1 and base.get("user") is None and not any(l.startswith("<user>") and l.endswith(f"/{name}.md") for l, _ in found):
        errs.append("the user has several procedures and none is named in the user's policy: set 'procedure' there, so the floor to keep is known")
    return found


def _runtime_policy(policy):
    """The policy values the runtime checks, as the numbers and lists it needs. A file holds text."""
    out, errs = {}, []
    for key in CAPS:
        if key in policy:
            raw = policy[key]
            if isinstance(raw, str) and WHOLE.match(raw):
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


def start_run(project, *, environ=None, name=None, allow_dirty=False, inline=None, trust="claims", run_id=None):
    """Freeze the resolved documents into a run. Returns None when there is nothing to run.

    Raises ResolutionError when the documents cannot start one."""
    got = resolve(project, environ=environ, name=name, allow_dirty=allow_dirty, inline=inline)
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
    ap.add_argument("--inline", metavar="FILE", help="JSON of policy, charter and procedures passed by a parent")
    a = ap.parse_args(argv)
    inline = None
    if a.inline:
        try:
            if os.path.getsize(a.inline) > MAX_INLINE_FILE:
                print(f"ERROR: --inline {a.inline}: too large (over {MAX_INLINE_FILE // 1024} KB)", file=sys.stderr)
                return 1
            with open(a.inline, encoding="utf-8") as f:
                inline = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"ERROR: --inline {a.inline}: {exc}", file=sys.stderr)
            return 1
    got = resolve(a.project, name=a.procedure, allow_dirty=a.allow_dirty, inline=inline)
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
