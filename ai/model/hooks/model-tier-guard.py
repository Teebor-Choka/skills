#!/usr/bin/env python3
"""PreToolUse hook (agent.spawn): every spawned subagent names its tier.

Tiers (light, execution, reasoning) and the model each one runs on, per harness, live in ONE file:
tiers.json at the plugin root (override the path with AGENT_TIERS_FILE; pick the harness with
AGENT_HARNESS, default "claude"). Tier keys are a fixed set (TIERS below); other keys are ignored, so an
explicit model name is never remapped. A value of "TODO", or a tier without a key for the harness, counts
as that one tier being absent. For the claude harness an absent tier falls back to BUILTIN. When the
harness has no usable model at all, or the map cannot be read, the hook fails open with a one-line
additionalContext note: it never guesses a model name for another harness.

`model` may be a harness model from the map or a tier name; a tier name is resolved through the map and
written back with hookSpecificOutput.updatedInput. For a built-in agent whose task is always one tier
(reading, search, extraction: never writing), DEFAULT_TIER fills `model` in the same way. For every other
agent the task's tier varies, so the call is denied unless `model` is one the map knows, forcing the
parent to pick the cheapest tier that does the task instead of inheriting its own model. The reasoning
tier can be chosen on purpose; it is never a default. Two further denials, both conservative (a false
denial costs more than a miss): a read-only agent with a short search-only prompt on a model other than
the light one, and the reasoning model on general-purpose unless the description or prompt names a
reasoning reason (architecture, design, adversarial review, novel debugging, root cause). Forks are
exempt: they always run on the parent model and ignore an override. Fails open on malformed input.
A model the Agent tool accepts but the map does not list (`fable`, a full `claude-...` id) passes through
unchanged on the claude harness. A rewrite carries updatedInput and no permissionDecision, so the user's own
permission rules still apply.
Tests: hooks/tests/test_model_tier_guard.py.
"""
import json
import os
import re
import sys

TIERS = ("light", "execution", "reasoning", "speed")

# Claude's own model names, used for a tier the map leaves absent (claude harness only).
BUILTIN = {"light": "haiku", "execution": "sonnet", "reasoning": "opus"}

# Agents whose role is always one tier, so it is never ambiguous: Claude built-ins and this plugin's own
# agents (bare or with the plugin prefix).
DEFAULT_TIER = {
    "Explore": "light",
    "claude-code-guide": "light",
    "statusline-setup": "light",
    "reader": "light",
    "builder": "execution",
    "reasoner": "reasoning",
}
PLUGIN_PREFIX = "models:"

DEFAULT_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tiers.json")

# Conservative on purpose: a false denial costs more than a miss. Search-only means a short prompt with a
# search verb and no analysis, review, design, or write word.
_SEARCH = re.compile(r"\b(find|locate|list|search|grep|look up|where is|where are|which files?)\b")
_NOT_SEARCH = re.compile(r"\b(review|audit|analy[sz]\w*|why|explain|design|architect\w*|adversarial|security|"
                         r"debug\w*|root.cause|evaluate|assess|compare|plan|implement\w*|fix\w*|write|"
                         r"summari[sz]\w*|bugs?)\b")
_REASONING = re.compile(r"architect|design|adversarial|novel|root.cause|threat.model|reasoning")
SEARCH_PROMPT_MAX = 800


def load_models():
    """({tier: model}, note) for the active harness. Placeholders and tiers without the harness key are
    dropped. note is a one-line reason when no model is usable (map unreadable, or nothing for the harness)."""
    harness = os.environ.get("AGENT_HARNESS") or "claude"
    path = os.environ.get("AGENT_TIERS_FILE") or DEFAULT_MAP
    try:
        with open(path) as f:
            tiers = json.load(f)["tiers"]
        models = {t: tiers[t].get(harness) for t in TIERS if isinstance(tiers.get(t), dict)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}, f"model-tier-guard is off: tier map {path} is missing or unreadable."
    models = {t: m for t, m in models.items() if isinstance(m, str) and m and m != "TODO"}
    if not models:
        return {}, f"model-tier-guard is off: tier map {path} has no model for harness {harness}."
    if harness == "claude":
        models = {**BUILTIN, **models}
    return models, ""


def reason_text(models):
    def m(tier):
        return models.get(tier, "(no model set)")
    return (
        f"Set `model` on every subagent: \"{m('light')}\" (tier light) for reading, search, extraction, "
        f"classification, log or diff scans, and status or poll loops; \"{m('execution')}\" (tier execution) "
        f"for implementing, writing code, tests, or docs, and routine debugging; \"{m('reasoning')}\" (tier "
        f"reasoning) only for architecture, design, novel debugging, and adversarial review (a reviewer on "
        f"the light tier misses what the gate exists to catch). A tier name is accepted too. Pick the "
        f"cheapest tier that does the task right, then re-dispatch one tier up only if it fails.")


def _text(tool_input, key):
    value = tool_input.get(key)
    return value.lower() if isinstance(value, str) else ""


def tier_violation(subagent_type, model, tool_input, models):
    """Deny reason for a model that is too expensive for the task, else ""."""
    kind = subagent_type.lower() if isinstance(subagent_type, str) else ""
    prompt = _text(tool_input, "prompt")
    light, reasoning = models.get("light"), models.get("reasoning")
    if (light and model != light
            and ("explore" in kind or "read-only" in kind or "readonly" in kind or kind == "review-only")
            and len(prompt) <= SEARCH_PROMPT_MAX and _SEARCH.search(prompt) and not _NOT_SEARCH.search(prompt)):
        return (f"This read-only agent has a search-only prompt (find, locate, list). Search and reading work "
                f"runs on model \"{light}\" (tier light). Set model to \"{light}\" or \"light\", or add the "
                f"analysis you need to the prompt.")
    if (reasoning and model == reasoning and kind in ("", "general-purpose")
            and not _REASONING.search(_text(tool_input, "description") + "\n" + prompt)):
        return (f"model \"{reasoning}\" (tier reasoning) needs a reasoning reason. State it in the description "
                f"or prompt (architecture, design, adversarial review, novel debugging, root cause), or use "
                f"\"{models.get('execution', 'the execution tier')}\" for implementing, writing, and routine "
                f"debugging.")
    return ""


def emit(decision, **fields):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             **fields}}))


def emit_rewrite(tool_input, model, why):
    """Rewrite `model` without a permissionDecision, so the user's own permission rules still apply.
    Unverified on the live runtime: if it ignores updatedInput without a decision, the spawn runs on the
    parent's model and additionalContext is the only trace."""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "updatedInput": {**tool_input, "model": model},
        "additionalContext": f"model-tier-guard: model set to \"{model}\" ({why})."}}))


def passes_through(model):
    """A model the Agent tool takes that the map does not list: `fable`, or a full id like claude-opus-4-1-2025.
    Claude harness only; the tier gates still apply to it, as an unknown model."""
    return (isinstance(model, str) and os.environ.get("AGENT_HARNESS", "claude") in ("", "claude")
            and (model == "fable" or re.fullmatch(r"claude-[a-z0-9][a-z0-9.-]*", model) is not None))


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
            return
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return
    except Exception:
        return
    subagent_type = tool_input.get("subagent_type")
    if subagent_type == "fork":
        return
    models, note = load_models()
    if not models:  # no usable model for this harness: nothing to enforce or resolve
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}))
        return
    model = tool_input.get("model")
    if isinstance(model, str) and model in models:  # a tier name: resolve it through the map
        resolved = models[model]
    elif model in models.values() or passes_through(model):
        resolved = None
    else:
        kind = subagent_type[len(PLUGIN_PREFIX):] if (isinstance(subagent_type, str)
                                                      and subagent_type.startswith(PLUGIN_PREFIX)) else subagent_type
        default_tier = DEFAULT_TIER.get(kind) if isinstance(kind, str) else None
        if default_tier in models:
            emit_rewrite(tool_input, models[default_tier], f"default for {subagent_type}, tier {default_tier}")
        else:
            emit("deny", permissionDecisionReason=reason_text(models))
        return
    reason = tier_violation(subagent_type, resolved or model, tool_input, models)
    if reason:
        emit("deny", permissionDecisionReason=reason)
    elif resolved:
        emit_rewrite(tool_input, resolved, f"tier {model}")


if __name__ == "__main__":
    main()
