#!/usr/bin/env python3
"""SessionStart hook: emit a one-line manifest of what this session can see.

The model learns up front which instruction files exist, how many global skills are installed, which
ancestor skill dirs the harness does NOT load on its own, and which provider it talks to. Must never block
a session: any failure prints nothing.

Inputs, none of them under ~/.claude:
  cwd           payload `cwd` (CLAUDE_PROJECT_DIR, then the process cwd, only when the payload has none)
  global skills AGENT_SKILLS_DIRS, directories separated by the path separator (AGENT_SKILLS_DIR is an
                alias). Unset: the line says so and names the variable.
  provider      ANTHROPIC_BASE_URL (host only, credentials dropped)

Claude Code loads project .claude/skills from cwd up to the git root (https://code.claude.com/docs/en/skills).
An ancestor .claude/skills ABOVE the git root (for example an org dir holding several repos) is not loaded,
so those are listed by skill name and path only; the model reads <path>/<name>/SKILL.md on demand. Skill
bodies are never inlined.
Tests: hooks/tests/test_session_manifest_record.py.
"""
import json
import os
import subprocess
import sys
from urllib.parse import urlparse

MAX_NAMES = 40


def skills_in(d):
    try:
        return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, "SKILL.md")))
    except OSError:
        return []


def payload_cwd():
    try:
        cwd = json.load(sys.stdin).get("cwd")
        return cwd if isinstance(cwd, str) and cwd else None
    except (ValueError, AttributeError):
        return None


def main():
    home = os.path.realpath(os.path.expanduser("~"))
    cwd = os.path.realpath(payload_cwd() or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

    def tilde(p):
        return "~" + p[len(home):] if p == home or p.startswith(home + os.sep) else p

    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        root = os.path.realpath(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else cwd
    except Exception:
        root = cwd

    configured = [p for var in ("AGENT_SKILLS_DIRS", "AGENT_SKILLS_DIR")
                  for p in os.environ.get(var, "").split(os.pathsep) if p]
    global_dirs = [os.path.realpath(p) for p in configured]
    instructions, skill_dirs, d = [], [], cwd
    while True:
        for rel in ("CLAUDE.md", "AGENTS.md", os.path.join(".claude", "CLAUDE.md")):
            if os.path.isfile(os.path.join(d, rel)):
                instructions.append(tilde(os.path.join(d, rel)))
        sk = os.path.join(d, ".claude", "skills")
        # $HOME/.claude/skills is the harness's own user-level dir, loaded natively: never an ancestor dir.
        if d != home and os.path.isdir(sk) and os.path.realpath(sk) not in global_dirs:
            skill_dirs.append((d, sk))
        if d == os.path.dirname(d):
            break
        d = os.path.dirname(d)

    def inside_root(p):
        return p == root or p.startswith(root + os.sep)

    parts = ["instructions: " + (", ".join(instructions) if instructions else "none found")]
    for g in global_dirs:
        parts.append(f"{len(skills_in(g))} skills in {tilde(g)}")
    if not global_dirs:
        parts.append("global skills unknown (set AGENT_SKILLS_DIRS)")
    for d, sk in skill_dirs:
        if inside_root(d):
            parts.append(f"{tilde(sk)} (auto-loaded)")
        else:
            names = skills_in(sk)
            if names:
                shown = ", ".join(names[:MAX_NAMES]) + (
                    f", +{len(names) - MAX_NAMES} more" if len(names) > MAX_NAMES else "")
                parts.append(f"{tilde(sk)} (above the git root, NOT auto-loaded; read <name>/SKILL.md on demand: {shown})")

    base = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    host = urlparse(base).hostname if base else None
    provider = f"custom base URL ({host or 'unparseable'})" if base else "native Anthropic"
    line = "Session manifest. " + "; ".join(parts) + "; provider: " + provider
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": line}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
