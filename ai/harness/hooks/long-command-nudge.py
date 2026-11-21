#!/usr/bin/env python3
"""PreToolUse hook (shell): once per session, advise on a slow foreground command.

A foreground nix build, flake check, cargo or docker build that runs with no stated expectation looks
stalled. For a command
matching a known slow shape without run_in_background, inject ONE additionalContext per session: state the
expected duration and a hard deadline up front, and prefer run_in_background. Advisory only: it never denies.

The command is split into segments with shlex (linear, no regex). A segment whose first word is a reader
(echo, grep, git, cat, ...) is text, not a build, so `echo "nix build"` and `git commit -m "cargo test"` stay
silent. Fails open on malformed input or an unwritable marker directory.
Tests: hooks/tests/test_long_command_nudge.py.
Schema: https://docs.claude.com/en/docs/claude-code/hooks
"""
import json
import os
import re
import shlex
import sys

_SEPARATOR_CHARS = set(";&|()\n")
_NON_EXEC = {"echo", "printf", "grep", "rg", "ag", "git", "cat", "man", "which", "type", "less", "head", "tail",
             "sed", "awk", "jq", "ls", "rm", "cp", "mv", "pip", "pip3", "uv", "brew", "gh"}
_SLOW_SUBCOMMANDS = {
    "cargo": {"build", "test", "nextest", "bench"},
    "npm": {"test"}, "pnpm": {"test"}, "yarn": {"test"},
    "go": {"test"},
    "make": {"test", "check"},
}

ADVICE = ("This foreground command is slow. Before you run it, say in one line the expected duration and a hard "
          "deadline (for example: about 5 min, stop at 10 min). Prefer run_in_background with a timeout, then "
          "check its output, over waiting in the foreground. If the deadline passes, check progress and report; "
          "do not keep waiting.")


def split_segments(command):
    lines, skip_until = [], None
    for line in command.split("\n"):  # heredoc bodies are text (commit messages), not commands
        if skip_until is not None:
            if line.strip() == skip_until:
                skip_until = None
            continue
        lines.append(line)
        # A heredoc opener: `<<` or `<<-` then a word. Not a here-string (`<<<`) and not shell arithmetic
        # (`$((1 << 3))`), which would swallow the lines after it.
        m = re.search(r"(?<!<)<<(?!<)-?\s*['\"]?([A-Za-z_]\w*)", re.sub(r"\$\(\(.*?\)\)", "", line))
        if m:
            skip_until = m.group(1)
    lex = shlex.shlex("\n".join(lines), posix=True, punctuation_chars="".join(_SEPARATOR_CHARS))
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    segments, cur = [], []
    for tok in lex:
        if tok and set(tok) <= _SEPARATOR_CHARS:
            if cur:
                segments.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segments.append(cur)
    return segments


def _subcommand(words, i):
    return next((w for w in words[i + 1:i + 6] if not w.startswith(("-", "+"))), "")


_ENV_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_PREFIXES = {"nohup", "time", "sudo", "command", "exec"}


def strip_wrappers(words):
    """Drop env assignments and wrappers (env, timeout, nice, nohup, time, sudo, uv run, uvx) in front of the
    real command. Anything else in front (ssh, a shell) keeps its own first word, so it is not a build."""
    words = list(words)
    while True:
        while words and _ENV_ASSIGN.fullmatch(words[0]):
            words.pop(0)
        if not words:
            return words
        head = os.path.basename(words[0])
        if head == "env":
            words.pop(0)
            while words and words[0].startswith("-"):
                words.pop(0)
        elif head == "timeout":
            words.pop(0)
            while words and words[0].startswith("-"):
                words.pop(0)
            if words:
                words.pop(0)  # the duration
        elif head == "nice":
            words.pop(0)
            if words[:1] == ["-n"]:
                del words[:2]
            elif words and words[0].startswith("-"):
                words.pop(0)
        elif head in _PREFIXES or head == "uvx":
            words.pop(0)
        elif head == "uv" and words[1:2] == ["run"]:
            del words[:2]
        else:
            return words


def is_slow(words):
    words = strip_wrappers(words)
    if not words or os.path.basename(words[0]) in _NON_EXEC:
        return False
    first = os.path.basename(words[0])
    rest = words[1:]
    if first == "nix":
        rest = rest[:6]
        return "build" in rest or any(rest[i:i + 2] == ["flake", "check"] for i in range(len(rest)))
    if first == "docker":
        return "build" in rest[:3]
    if first == "pytest" or (first.startswith("python") and rest[:2] == ["-m", "pytest"]):
        return True
    return first in _SLOW_SUBCOMMANDS and _subcommand(words, 0) in _SLOW_SUBCOMMANDS[first]


def advice_due(command):
    try:
        return any(is_slow(words) for words in split_segments(command))
    except ValueError:
        return False


def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value)).lstrip(".") or "none"


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            return
        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command")
        if not isinstance(command, str) or tool_input.get("run_in_background") or not advice_due(command):
            return
        marker = os.path.join(os.environ.get("TMPDIR") or "/tmp",
                              "agent-long-command-expectation." + safe(data.get("session_id") or f"nosession-{os.getuid()}"))
        try:  # exclusive and no-follow: a planted symlink is never written through
            os.close(os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600))
        except FileExistsError:
            return  # advised already
        except OSError:
            return  # cannot remember the advice: stay silent rather than repeat it on every command
    except Exception:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ADVICE}}))


if __name__ == "__main__":
    main()
