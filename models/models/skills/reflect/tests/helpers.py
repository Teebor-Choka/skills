"""Shared builders for the reflect tests: small synthetic transcripts, no real data."""
import importlib.util
import json
import pathlib

SKILL = pathlib.Path(__file__).resolve().parent.parent


def load(filename):
    path = SKILL / filename
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def at(row, ts):
    return {**row, "timestamp": ts}


def asst_tool(name, inp, msg_id=None, use_id=None, model=None, usage=None):
    block = {"type": "tool_use", "name": name, "input": inp}
    if use_id:
        block["id"] = use_id
    message = {"content": [block]}
    if msg_id:
        message["id"] = msg_id
    if model:
        message["model"] = model
    if usage:
        message["usage"] = usage
    return {"type": "assistant", "message": message}


def asst_text(text="ok", msg_id=None, model=None, usage=None):
    message = {"content": [{"type": "text", "text": text}]}
    if msg_id:
        message["id"] = msg_id
    if model:
        message["model"] = model
    if usage:
        message["usage"] = usage
    return {"type": "assistant", "message": message}


def user_text(text, **extra):
    return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}, **extra}


def tool_result(text, use_id=None):
    block = {"type": "tool_result", "content": text}
    if use_id:
        block["tool_use_id"] = use_id
    return {"type": "user", "message": {"content": [block]}}


def write(tmp_path, rows, name="s.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)
