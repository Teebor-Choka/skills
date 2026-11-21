#!/usr/bin/env python3
"""SessionStart hook: check that the hooks it can see point at files that exist.

Usage: hook-doctor.py [--check] [--settings FILE ...] [plugin-root ...]
  (default) SessionStart mode: problems go out as hookSpecificOutput additionalContext and the exit code is
            0, because Claude Code reads SessionStart stdout as context only on exit 0. Silent when clean.
  --check   plain text, one line per problem, exit 1 on any problem (for CI and the command line).
  plugin roots   arguments, else AGENT_PLUGIN_ROOTS (path-separator list), else the plugin that holds this
                 script. For each: hooks/manifest.json parses and follows the manifest rules (id, event,
                 script, enforce, tools, matcher), every script it names exists and is executable, and every
                 command in hooks/hooks.json points at an existing, executable file.
  settings files --settings flags, else AGENT_SETTINGS_FILES (path-separator list). Nothing is read from
                 ~/.claude unless you name it. Every hook command in them must resolve.
A command's first word is checked: $VARS and ~ are expanded, a path must exist, a bare name must be on PATH.
Malformed JSON or an unexpected shape is reported as a problem, never a traceback. It does not render
hooks.json: the repo's flake check compares that.
A command that uses ${CLAUDE_PLUGIN_ROOT} in a settings file is listed as unverifiable (not a failure)
unless the variable is set in the environment, since only a plugin-scoped run knows the root.
Tests: hooks/tests/test_hook_doctor.py.
"""
import json
import os
import shlex
import shutil
import sys

EVENTS = {"session.start", "session.end", "prompt.submit", "tool.before", "tool.after", "subagent.start",
          "stop", "compact"}
TOOLS = {"shell", "file.read", "file.edit", "agent.spawn", "ask.user", "message.send", "wake.schedule"}
TOOL_EVENTS = {"tool.before", "tool.after"}
UNVERIFIABLE = " is unverifiable here"
PLUGIN_ROOT_VARS = ("${CLAUDE_PLUGIN_ROOT}", "$CLAUDE_PLUGIN_ROOT")


def load(path):
    try:
        with open(path) as f:
            return json.load(f), None
    except OSError:
        return None, "does not exist or is unreadable"
    except ValueError as e:
        return None, f"is not valid JSON ({e})"


def script_problem(root, rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return f"script {rel} does not exist"
    if not os.access(path, os.X_OK):
        return f"script {rel} is not executable"
    return None


def manifest_problems(root):
    manifest, err = load(os.path.join(root, "hooks", "manifest.json"))
    if err:
        yield f"hooks/manifest.json {err}"
        return
    hooks = manifest.get("hooks") if isinstance(manifest, dict) else None
    if not isinstance(hooks, list):
        yield "hooks/manifest.json: hooks must be a list"
        return
    seen = set()
    for i, h in enumerate(hooks):
        h = h if isinstance(h, dict) else {}
        label = f"hook {h['id']}" if isinstance(h.get("id"), str) else f"hook #{i}"
        if not isinstance(h.get("id"), str):
            yield f"{label}: missing id"
        elif h["id"] in seen:
            yield f"{label}: duplicate id"
        else:
            seen.add(h["id"])
        event = h.get("event")
        if event not in EVENTS:
            yield f"{label}: unknown or missing event {event!r}"
        script = h.get("script")
        if not isinstance(script, str):
            yield f"{label}: missing script"
        elif script.startswith("/") or ".." in script.split("/") or any(c in script for c in "\"$`"):
            yield f"{label}: script must be a relative path without .., quote, $ or backtick"
        else:
            problem = script_problem(root, script)
            if problem:
                yield f"{label}: {problem}"
        if h.get("enforce") not in ("block", "warn"):
            yield f"{label}: enforce must be block or warn"
        tools = h.get("tools")
        if tools is not None:
            if event not in TOOL_EVENTS:
                yield f"{label}: tools apply only to tool.before and tool.after"
            for t in tools if isinstance(tools, list) else [tools]:
                if t not in TOOLS:
                    yield f"{label}: unknown tool {t!r}"
        if event == "compact" and ("matcher" in h or tools is not None):
            yield f"{label}: compact takes no tools or matcher"


def command_problems(doc, label, plugin_root=None):
    plugin_root = plugin_root or os.environ.get("CLAUDE_PLUGIN_ROOT") or None
    hooks = doc.get("hooks") if isinstance(doc, dict) else None
    if hooks is None and isinstance(doc, dict):
        return  # a settings file with no hooks has nothing to check
    if not isinstance(hooks, dict):
        yield f"{label}: unexpected shape, expected an object with a `hooks` object"
        return
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            yield f"{label} [{event}]: unexpected shape, expected a list of groups"
            continue
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                yield f"{label} [{event}]: unexpected shape, a group needs a `hooks` list"
                continue
            for hook in entries:
                command = hook.get("command") if isinstance(hook, dict) else None
                if not isinstance(command, str):
                    if not (isinstance(hook, dict) and hook.get("type", "command") != "command"):
                        yield f"{label} [{event}]: a hook entry has no string `command`"
                    continue
                if any(var in command for var in PLUGIN_ROOT_VARS):
                    if not plugin_root:
                        yield f"{label} [{event}]: {command}{UNVERIFIABLE} (CLAUDE_PLUGIN_ROOT is not set)"
                        continue
                    for var in PLUGIN_ROOT_VARS:
                        command = command.replace(var, plugin_root)
                try:
                    words = shlex.split(os.path.expanduser(os.path.expandvars(command)))
                except ValueError:
                    continue
                if not words:
                    continue
                target = os.path.expanduser(words[0])
                if "/" in target:
                    if not os.path.isfile(target):
                        yield f"{label} [{event}]: {target} does not exist"
                    elif plugin_root and not os.access(target, os.X_OK):
                        yield f"{label} [{event}]: {target} is not executable"
                elif not shutil.which(target):
                    yield f"{label} [{event}]: {target} is not on PATH"


def hooks_json_problems(root):
    doc, err = load(os.path.join(root, "hooks", "hooks.json"))
    if err:
        yield f"hooks/hooks.json {err}"
        return
    yield from command_problems(doc, "hooks/hooks.json", root)


def paths(var):
    return [p for p in os.environ.get(var, "").split(os.pathsep) if p]


def main(argv):
    settings, roots, args, check = [], [], argv[1:], False
    while args:
        arg = args.pop(0)
        if arg == "--check":
            check = True
        elif arg == "--settings" and args:
            settings.append(args.pop(0))
        else:
            roots.append(arg)
    settings = settings or paths("AGENT_SETTINGS_FILES")
    roots = roots or paths("AGENT_PLUGIN_ROOTS") or [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    problems = []
    for path in settings:
        doc, err = load(path)
        if err:
            problems.append(f"{path}: {err}")
        else:
            problems += list(command_problems(doc, path))
    for root in roots:
        problems += [f"{root}: {p}" for p in (*manifest_problems(root), *hooks_json_problems(root))]
    notes = [p for p in problems if UNVERIFIABLE in p]  # reported, but not a failure
    problems = [p for p in problems if UNVERIFIABLE not in p]
    if check:
        for line in problems + notes:
            print(line)
        return 1 if problems else 0
    if problems:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "hook-doctor found problems:\n" + "\n".join(problems)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
