#!/usr/bin/env python3
"""Resolve a development policy for a repo — stdlib only, open and layered.

A skill reads its configuration from here instead of hardcoding a process constant. The
policy lives in `.agents/policy.md` (frontmatter = machine keys; body = prose pointers).
It is OPTIONAL and LAYERED: a small built-in baseline, overlaid by a global policy, overlaid
by a local per-repo policy (local wins per key). Nothing requires the files to exist; their
absence resolves to the baseline — a reasonable, almost-basic default.

Open schema: any key is allowed. The loader does not police a fixed set, so a new skill can
read a new key with no change here. "Malformed" means a structural error (no frontmatter, a
bad list, an indented line with no parent) — never an unknown key.

Per-skill overrides: a frontmatter key whose value is a nested map is a section. A section
named after a skill overrides the global key for that skill only. Resolution for a skill
reading key K:  local <skill>.K  ->  local K  ->  global <skill>.K  ->  global K  ->
baseline[K]  ->  the skill's own fallback (the `default` passed to get()).

Usage:
    policy_loader.py <repo> [--global FILE] [--json]          # print the resolved policy
    policy_loader.py <repo> --get KEY [--skill NAME]          # print one resolved value
    policy_loader.py --selfcheck                              # run the acceptance checks
"""
import argparse
import copy
import fnmatch
import json
import os
import sys

# The reasonable, almost-basic default when no policy is present. Single actor, no fleet
# (the parallel path is opt-in via mode: team); the grilling rhythm is batch; grounding uses
# whatever index/tool is present ("auto"); acceptance is a plain checklist unless a practice
# says otherwise. Any of these is overridable by a policy file; skills may read other keys
# not listed here and supply their own fallback.
BASELINE = {
    "mode": "single",        # single | team
    "interaction": "batch",  # batch | dialog
    "grounding": "auto",     # auto | none | <tool name>
    "gate": "plain",         # plain | tests | rubric
    "practices": {},         # e.g. {scope: ATDD, task: TDD}; empty = none forced
}


class PolicyError(ValueError):
    """A policy file is structurally malformed; the message names where."""


# ---------------------------------------------------------------- parsing

def _split_frontmatter(text, src):
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        raise PolicyError(f"{src}: no frontmatter block (expected a leading '---' fence)")
    body = []
    for line in lines[i + 1:]:
        if line.strip() == "---":
            return "\n".join(body)
        body.append(line)
    raise PolicyError(f"{src}: unterminated frontmatter (missing closing '---')")


def _strip_inline_comment(v):
    """Drop a trailing ` # ...` comment that sits outside quotes and brackets."""
    depth, quote = 0, None
    for i, c in enumerate(v):
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "[({":
            depth += 1
        elif c in "])}":
            depth = max(0, depth - 1)
        elif c == "#" and depth == 0 and (i == 0 or v[i - 1].isspace()):
            return v[:i].strip()
    return v.strip()


def _scalar(raw):
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    return v


def _inline_list(raw, key, src, lineno):
    v = raw.strip()
    if not (v.startswith("[") and v.endswith("]")):
        raise PolicyError(f"{src}:{lineno}: key '{key}' list must look like [a, b], got {v!r}")
    inner = v[1:-1].strip()
    return [_scalar(x) for x in inner.split(",") if x.strip()] if inner else []


def _unquote_key(k):
    k = k.strip()
    if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
        k = k[1:-1]
    return k


def _parse_frontmatter(block, src):
    """Open YAML subset: scalars, inline lists, and nested maps by indentation (any depth).

    Nesting carries the per-skill sections and the `files:` glob-override map (glob -> overrides)."""
    root = {}
    stack = [(-1, root)]  # (indent of the key that opened this container, container dict)
    for lineno, line in enumerate(block.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise PolicyError(f"{src}:{lineno}: not a 'key: value' line: {line.strip()!r}")
        indent = len(line) - len(line.lstrip())
        rawkey, _, val = line.lstrip().partition(":")
        key = _unquote_key(rawkey)
        val = _strip_inline_comment(val)
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not isinstance(parent, dict):
            raise PolicyError(f"{src}:{lineno}: '{key}' is nested under a non-map value")
        if val == "":                     # `key:` alone opens a nested map
            m = {}
            parent[key] = m
            stack.append((indent, m))
        elif val.startswith("["):
            parent[key] = _inline_list(val, key, src, lineno)
        else:
            parent[key] = _scalar(val)
    return root


def _load_file(path):
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return _parse_frontmatter(_split_frontmatter(f.read(), path), path)


# ---------------------------------------------------------------- resolution

def _overlay(base, overlay, provenance, label):
    """Per-key overlay; a dict value merges one level, anything else replaces."""
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            for sk, sv in val.items():
                base[key][sk] = sv
                provenance[f"{key}.{sk}"] = label
        else:
            base[key] = val
            provenance[key] = label


def resolve(repo_path, global_path=None):
    """Resolve a policy object for repo_path: baseline < global < local, per key."""
    if not os.path.isdir(repo_path):
        raise PolicyError(f"repo path is not a directory: {repo_path}")
    resolved = copy.deepcopy(BASELINE)
    provenance = {k: "baseline" for k in BASELINE}
    if global_path is None:
        global_path = os.environ.get("AGENTS_POLICY_GLOBAL") or \
            os.path.join(os.path.expanduser("~"), ".agents", "policy.md")
    g = _load_file(global_path)
    if g is not None:
        _overlay(resolved, g, provenance, "global")
    local = _load_file(os.path.join(repo_path, ".agents", "policy.md"))
    if local is not None:
        _overlay(resolved, local, provenance, "local")
    resolved["_provenance"] = provenance
    return resolved


def _glob_specificity(g):
    """Rank a glob: more path segments, then more literal (non-wildcard) characters, wins."""
    return (g.count("/"), len(g.replace("*", "").replace("?", "")))


def get(resolved, key, skill=None, target=None, default=None):
    """Read one key. Precedence (most specific first):

      1. a per-file rule — the most specific `files:` glob matching `target` that defines the key
      2. a per-skill section — `<skill>.key`
      3. the global key
      4. `default` — the skill's own fallback for a key the baseline does not define

    `target` is the path (relative to the repo) the skill is acting on; omit it for a repo-wide read."""
    if target and isinstance(resolved.get("files"), dict):
        hits = [(g, ov[key]) for g, ov in resolved["files"].items()
                if isinstance(ov, dict) and key in ov and fnmatch.fnmatch(target, g)]
        if hits:
            hits.sort(key=lambda h: _glob_specificity(h[0]))
            return hits[-1][1]
    if skill and isinstance(resolved.get(skill), dict) and key in resolved[skill]:
        return resolved[skill][key]
    if key in resolved:
        return resolved[key]
    return default


# ---------------------------------------------------------------- cli + selfcheck

def _selfcheck():
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")

    with tempfile.TemporaryDirectory() as d:
        empty_global = os.path.join(d, "no-global.md")
        # 1. no policy anywhere -> baseline
        r = resolve(d, global_path=empty_global)
        check("no policy -> baseline (mode=single, interaction=batch)",
              r["mode"] == "single" and r["interaction"] == "batch")
        # 2. global only -> global used
        gpath = os.path.join(d, "global.md")
        with open(gpath, "w") as f:
            f.write("---\ninteraction: dialog\ntoolchain: [codegraph, pytest]\n---\n")
        r = resolve(d, global_path=gpath)
        check("global only -> global used", r["interaction"] == "dialog"
              and r["toolchain"] == ["codegraph", "pytest"])
        # 3. local overrides global, per key
        os.makedirs(os.path.join(d, ".agents"))
        with open(os.path.join(d, ".agents", "policy.md"), "w") as f:
            f.write('---\ninteraction: batch\nramble:\n  interaction: dialog\n'
                    'files:\n  "*.md":\n    gate: rubric\n  "docs/*.md":\n    gate: plain\n---\n')
        r = resolve(d, global_path=gpath)
        check("local overrides global per key", r["interaction"] == "batch")
        check("global key kept where local is silent", r["toolchain"] == ["codegraph", "pytest"])
        # 4. per-skill section overrides the global key for that skill
        check("per-skill section: ramble.interaction=dialog",
              get(r, "interaction", skill="ramble") == "dialog")
        check("per-skill falls through to global for other skills",
              get(r, "interaction", skill="architect") == "batch")
        # 4b. per-file glob override (most specific wins); no match -> baseline
        check("per-file: *.md -> gate rubric", get(r, "gate", target="notes.md") == "rubric")
        check("per-file: more specific docs/*.md wins",
              get(r, "gate", target="docs/readme.md") == "plain")
        check("per-file: no glob match -> baseline gate=plain",
              get(r, "gate", target="main.py") == "plain")
        # 5. unknown key passes through (open schema), skill default for absent key
        check("unknown key absent -> skill's own default",
              get(r, "verbosity", default="normal") == "normal")
        # 6. malformed -> loud error, no silent fallback
        bad = os.path.join(d, "bad.md")
        with open(bad, "w") as f:
            f.write("no frontmatter here\n")
        try:
            _load_file(bad)
            check("malformed -> PolicyError", False)
        except PolicyError:
            check("malformed -> PolicyError (named)", True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path", nargs="?")
    ap.add_argument("--global", dest="global_path", default=None)
    ap.add_argument("--get", dest="key", default=None)
    ap.add_argument("--skill", default=None)
    ap.add_argument("--target", default=None, help="the file a skill acts on (for per-file rules)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args(argv)
    if args.selfcheck:
        return _selfcheck()
    if not args.repo_path:
        ap.error("repo_path is required (or use --selfcheck)")
    try:
        resolved = resolve(args.repo_path, args.global_path)
    except PolicyError as e:
        print(f"POLICY ERROR: {e}", file=sys.stderr)
        return 2
    if args.key:
        print(get(resolved, args.key, skill=args.skill, target=args.target))
    elif args.json:
        print(json.dumps(resolved, indent=2, sort_keys=True))
    else:
        for k, v in resolved.items():
            if k != "_provenance":
                print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
