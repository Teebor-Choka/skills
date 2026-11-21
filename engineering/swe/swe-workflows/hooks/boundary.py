#!/usr/bin/env python3
"""Map a pending Bash call (hook payload JSON on stdin) to an integration boundary.

Prints `<boundary> [<pr-number>]` (commit, ready, integrate) or nothing. A boundary word counts only
at the head of a command segment (after env assignments and wrappers), so a commit message, a heredoc
body, an `echo` or a `grep` that merely mentions `git merge` is not a boundary.
"""
import json
import re
import shlex
import sys

SEP = set(";&|()\n")
WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo"}
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1[^\n]*")
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def strip_heredocs(cmd):
    """Drop heredoc bodies (linear scan; an unterminated one is left alone)."""
    out, pos = [], 0
    for m in HEREDOC.finditer(cmd):
        if m.start() < pos:
            continue
        eol = cmd.find("\n", m.end())
        if eol < 0:
            continue
        i = eol + 1
        while i <= len(cmd):
            j = cmd.find("\n", i)
            line = cmd[i:] if j < 0 else cmd[i:j]
            if line.strip() == m.group(2):
                out.append(cmd[pos:eol])
                pos = len(cmd) if j < 0 else j
                break
            if j < 0:
                break
            i = j + 1
    out.append(cmd[pos:])
    return "".join(out)


def segments(cmd):
    lex = shlex.shlex(strip_heredocs(cmd), posix=True, punctuation_chars="".join(SEP))
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    segs, cur = [], []
    for tok in lex:
        if tok and set(tok) <= SEP:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def head(words):
    while words:
        if re.match(r"[A-Za-z_][A-Za-z0-9_]*=", words[0]) or words[0] in ("do", "then", "else"):
            words = words[1:]
        elif words[0] in WRAPPERS:
            words = words[1:]
            while words and words[0].startswith("-"):
                words = words[1:]
        else:
            break
    return words


def git_sub(words):
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GIT_OPTS_WITH_VALUE else 1
    return (words[i], words[i + 1:]) if i < len(words) else (None, [])


def boundary(cmd):
    for words in map(head, segments(cmd)):
        if len(words) < 2:
            continue
        tool = words[0].rsplit("/", 1)[-1]
        if tool == "git":
            sub, _ = git_sub(words)
            if sub == "commit":
                return "commit", ""
            if sub == "merge":
                return "integrate", ""
        elif tool in ("gh", "glab") and len(words) >= 3:
            noun, verb = words[1], words[2]
            if (noun, verb) in (("pr", "create"), ("mr", "create"), ("pr", "ready"), ("mr", "ready")):
                return "ready", ""
            if (noun, verb) == ("pr", "edit") and "--ready" in words:
                return "ready", ""
            if (noun, verb) in (("pr", "merge"), ("mr", "merge")):
                ref = next((w.lstrip("#") for w in words[3:] if re.fullmatch(r"#?\d+", w)), "")
                return "integrate", ref
    return None


def main():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or data).get("command")
    except Exception:
        return
    if not isinstance(cmd, str):
        return
    try:
        found = boundary(cmd)
    except ValueError:
        return
    if found:
        print(*[x for x in found if x])


if __name__ == "__main__":
    main()
