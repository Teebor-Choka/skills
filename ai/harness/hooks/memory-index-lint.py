#!/usr/bin/env python3
"""SessionStart hook: report skill names in a memory index that no installed skill matches.

A memory index can keep pointing at a skill that was removed. A skill reference is a backticked name next to
the word "skill": `name` skill, or skill `name`. A `plugin:skill` name matches on its last part. A skill
exists when a directory of that name holds a SKILL.md under one of the skill roots (searched four levels
deep, symlinks followed).

Inputs, none of them under ~/.claude:
  memory index  <dir of payload transcript_path>/memory/MEMORY.md (Claude Code keeps the index beside the
                session transcript), plus every file matched by AGENT_MEMORY_FILES (glob patterns separated
                by the path separator)
  skill roots   AGENT_SKILLS_DIRS (directories separated by the path separator; AGENT_SKILLS_DIR is an
                alias). With no root configured nothing can be judged, so the hook prints one line naming
                the variable and exits 0: silence would look like a clean run.
Report only. Default (SessionStart) mode prints the problems as hookSpecificOutput additionalContext and
exits 0, because Claude Code reads SessionStart stdout as context only on exit 0; silent when clean. With
--check it prints one plain line per dangling name per file and exits 1. Never
edits a memory file. Fails open on malformed input.
Tests: hooks/tests/test_memory_index_lint.py.
"""
import glob
import json
import os
import re
import sys

MAX_DEPTH = 4
NAME_BEFORE = re.compile(r"`([A-Za-z0-9][A-Za-z0-9_.:-]*)`\s+skill\b", re.IGNORECASE)
NAME_AFTER = re.compile(r"\bskill\s+`([A-Za-z0-9][A-Za-z0-9_.:-]*)`", re.IGNORECASE)


def paths(var):
    return [p for p in os.environ.get(var, "").split(os.pathsep) if p]


def skill_roots():
    return paths("AGENT_SKILLS_DIRS") + paths("AGENT_SKILLS_DIR")


def installed_skills(roots):
    names = set()
    for root in roots:
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
            if dirpath.count(os.sep) - base_depth >= MAX_DEPTH:
                dirnames[:] = []
            if "SKILL.md" in filenames:
                names.add(os.path.basename(dirpath))
    return names


def referenced(text):
    seen = []
    for rx in (NAME_BEFORE, NAME_AFTER):
        for m in rx.finditer(text):
            if m.group(1) not in seen:
                seen.append(m.group(1))
    return seen


def memory_files():
    files = []
    try:
        transcript = json.load(sys.stdin).get("transcript_path")
        if isinstance(transcript, str) and transcript:
            files.append(os.path.join(os.path.dirname(transcript), "memory", "MEMORY.md"))
    except (ValueError, AttributeError):
        pass
    for pattern in paths("AGENT_MEMORY_FILES"):
        files += glob.glob(os.path.expanduser(pattern))
    return sorted({f for f in files if os.path.isfile(f)})


def report(lines, check):
    if check:
        for line in lines:
            print(line)
        return 1 if lines else 0
    if lines:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n".join(lines)}}))
    return 0


def main():
    check = "--check" in sys.argv[1:]
    roots = skill_roots()
    if not roots:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
              "memory-index-lint: not run. Set AGENT_SKILLS_DIRS to the skill directories to check against."}})
              if not check else "memory-index-lint: not run. Set AGENT_SKILLS_DIRS to the skill directories to check against.")
        return 0
    files = memory_files()
    if not files:
        return 0
    skills = None
    problems = []
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for name in referenced(text):
            if skills is None:
                skills = installed_skills(roots)
            if name.rsplit(":", 1)[-1] not in skills:
                problems.append(f"{path}: skill `{name}` not found in {', '.join(roots)}")
    return report(problems, check)


if __name__ == "__main__":
    sys.exit(main())
