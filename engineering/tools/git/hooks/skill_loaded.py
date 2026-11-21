"""Has this agent loaded a skill? The one transcript scan shared by skill-gate and git-guard.

Plugins install independently, so each plugin that needs this ships a byte-identical copy next to its
hook (a test in `git` pins the copies together). Import it with the hook's own directory on sys.path.

skill_loaded(payload, skill, aliases, state_dir) -> True | False | None
  True   the agent's own transcript shows the skill loaded; cached as a marker file per session, agent, skill
  False  the transcript was read and shows no load
  None   no usable transcript (unknown path, non-string path, missing file); the caller picks fail-open or
         fail-closed

A load is accepted only in a shape the harness writes, found by parsing each transcript line as JSON:
  - an assistant `tool_use` named Skill whose input `skill` is the skill or an alias (optional `plugin:` prefix)
  - a user message whose own text (a string, or a text block, never a tool_result) starts with
    `<command-message>skill</command-message>` (the slash-command tag)
Text inside a tool result, assistant text or a command string never counts. The "Base directory for this
skill" banner never counts either: a user can type it, so it could forge the gate.

A subagent payload carries the parent's transcript_path plus agent_id. The subagent's own transcript is
<session>/subagents/agent-<agent_id>.jsonl, so each agent must load a skill itself.
"""
import json
import os
import re
import tempfile


def _safe(value):
    return re.sub(r"[^\w.-]", "_", str(value or "")).lstrip(".")


def _names(skill, aliases):
    return "|".join(re.escape(n) for n in (skill, *aliases))


def _matchers(skill, aliases):
    names = _names(skill, aliases)
    call = re.compile(rf"(?:[\w.-]+:)?(?:{names})")
    tag = re.compile(rf"\s*<command-message>(?:[\w.-]+:)?(?:{names})</command-message>")
    return call, tag


def _user_texts(message):
    content = message.get("content")
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                yield block["text"]


def _is_load(entry, call, tag):
    message = entry.get("message")
    if not isinstance(message, dict):
        return False
    if entry.get("type") == "assistant":
        content = message.get("content")
        for block in content if isinstance(content, list) else ():
            if (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"
                    and isinstance((block.get("input") or {}).get("skill"), str)
                    and call.fullmatch(block["input"]["skill"])):
                return True
    elif entry.get("type") == "user":
        for text in _user_texts(message):
            if tag.match(text):
                return True
    return False


def scan(path, skill, aliases=()):
    """True/False for a readable transcript, None when it cannot be read. Streams it line by line."""
    call, tag = _matchers(skill, aliases)
    try:
        with open(path, "rb") as f:
            for line in f:
                if b"skill" not in line and b"command-message" not in line:
                    continue  # cheap prefilter: parsing every line of a long transcript is slow
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and _is_load(entry, call, tag):
                    return True
    except OSError:
        return None
    return False


def skill_loaded(payload, skill, aliases=(), state_dir=None):
    try:
        state_dir = state_dir or os.environ.get("AGENT_STATE_DIR") or \
            os.path.join(tempfile.gettempdir(), "agent-skill-loaded")
        sid = _safe(payload.get("session_id"))
        path = payload.get("transcript_path")
        if not isinstance(path, str) or not path:
            return None
        agent = _safe(payload.get("agent_id"))
        if agent:
            sid = f"{sid}.agent-{agent}" if sid else ""
            path = os.path.join(os.path.splitext(path)[0], "subagents", f"agent-{agent}.jsonl")
        marker = os.path.join(state_dir, f"{sid}.{_safe(skill)}") if sid else None
        if marker and os.path.exists(marker):
            return True
        if not os.path.isfile(path):
            return None
        found = scan(path, skill, aliases)
        if found and marker:
            try:
                os.makedirs(state_dir, exist_ok=True)
                open(marker, "w").close()
            except OSError:
                pass
        return found
    except Exception:
        return None
