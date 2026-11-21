"""Tests for reflectlib.py: turn classification, hook outcomes, secret scrubbing."""
import pytest

from helpers import load, tool_result, user_text

lib = load("reflectlib.py")


# --- RF-06: one classifier for every kind of user-side entry ----------------

@pytest.mark.parametrize("entry,want", [
    (user_text("please add a test for the parser"), "human"),
    (user_text("Base directory for this skill: /x/skills/foo\n\n# Foo"), "skill_body"),
    (user_text("body of a skill", isMeta=True, sourceToolUseID="t1"), "skill_body"),
    (user_text("This session is being continued from a previous conversation that ran out "
               "of context."), "compaction_summary"),
    ({"type": "user", "isCompactSummary": True, "message": {"content": "summary"}},
     "compaction_summary"),
    (user_text('<cross-session-message from="a">hi</cross-session-message>'), "peer"),
    (user_text("hello", origin={"kind": "peer"}), "peer"),
    (user_text("<task-notification><task-id>a</task-id></task-notification>"),
     "task_notification"),
    (user_text("<command-name>/review</command-name>"), "slash_command"),
    (user_text("<system-reminder>be brief</system-reminder>"), "injected"),
    (user_text("meta text", isMeta=True), "injected"),
    (tool_result("ok"), "tool_result"),
    ({"type": "attachment", "attachment": {"type": "queued_command", "prompt": "also fix y"}},
     "queued"),
])
def test_classify_user_turn(entry, want):
    assert lib.classify_user_turn(entry) == want


def test_only_a_human_turn_counts_as_human():
    kinds = {lib.classify_user_turn(e) for e in (
        user_text("<system-reminder>no, stop</system-reminder>"),
        user_text("Base directory for this skill: /x"),
        user_text("<command-name>/x</command-name>"))}
    assert "human" not in kinds


# --- RF-05: hook outcomes ----------------------------------------------------

@pytest.mark.parametrize("att,want", [
    ({"type": "hook_blocking_error", "hookName": "PreToolUse:Bash", "exitCode": 2}, "deny"),
    ({"type": "hook_non_blocking_error", "hookName": "h", "exitCode": 1}, "nonblocking"),
    ({"type": "hook_success", "hookName": "h", "exitCode": 1}, "nonblocking"),
    ({"type": "hook_success", "hookName": "h", "exitCode": 2}, "deny"),
    ({"type": "hook_additional_context", "hookName": "h", "content": ["note"]}, "context"),
    ({"type": "hook_success", "hookName": "h", "exitCode": 0, "content": ""}, None),
    ({"type": "skill_listing"}, None),
])
def test_classify_hook_event(att, want):
    assert lib.classify_hook_event(att) == want


def test_a_hook_claimed_to_block_that_never_denies_is_flagged():
    hooks = {"gate.sh": {"deny": 0, "nonblocking": 7, "context": 0},
             "ok.sh": {"deny": 3, "nonblocking": 0, "context": 0},
             "idle.sh": {"deny": 0, "nonblocking": 0, "context": 2}}
    assert lib.flag_blocking_claims(hooks, ["gate.sh", "ok.sh", "idle.sh"]) == ["gate.sh"]


def test_tool_result_hook_denial_gives_hook_name_and_a_short_scrubbed_reason():
    name, reason = lib.tool_result_hook_denial(
        "PreToolUse:Bash hook error: token=abcd1234secret " + "x" * 200)
    assert name == "PreToolUse:Bash"
    assert len(reason) <= 80 and "abcd1234secret" not in reason


@pytest.mark.parametrize("text", ["plain output", "", None,
                                  "see PreToolUse:Bash hook error: quoted"])
def test_other_tool_results_are_not_hook_denials(text):
    assert lib.tool_result_hook_denial(text) is None


# --- RF-08: secret scrubbing -------------------------------------------------

@pytest.mark.parametrize("text,secret", [
    ("db password=hunter2 ok", "hunter2"),
    ("export API_KEY='abc'", "abc"),
    ("token: s3cr3t", "s3cr3t"),
    ("Authorization: Bearer abcDEF123xyz", "abcDEF123xyz"),
    ("key AKIAABCDEFGHIJKLMNOP here", "AKIAABCDEFGHIJKLMNOP"),
    ("ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8", "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"),
    ("-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----", "MIIabc"),
    ("blob " + "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZjEyMzQ1Njc4OTA", "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZjEyMzQ1Njc4OTA"),
])
def test_scrub_redacts_secrets(text, secret):
    out = lib.scrub(text)
    assert secret not in out
    assert "[redacted" in out


def test_scrub_keeps_a_long_worktree_path():
    path = ("/Users/me/repo/.claude/worktrees/feature-0123456789abcdef0123456789abcdef"
            "/ai/model/skills/reflect/SKILL.md")
    assert lib.scrub(f"edited {path} twice") == f"edited {path} twice"


def test_scrub_keeps_plain_prose_and_short_words():
    text = "the password policy page lists token types"
    assert lib.scrub(text) == text


def test_output_of_a_secret_printing_command_is_redacted():
    assert lib.scrub_result("cat ~/.config/app/token", "plainsecretvalue") != "plainsecretvalue"
    assert lib.scrub_result("security find-generic-password -w -s x", "x9") != "x9"
    assert lib.scrub_result("ls -la", "total 4") == "total 4"


# --- cost state belongs to the harness adapter, not to cost.py ---------------

@pytest.mark.parametrize("entry,want", [
    ({"type": "cost-state", "totalCostUsd": 2.5}, (2.5, False)),
    ({"type": "cost-state", "totalCostUSD": 1, "hasUnknownModelCost": True}, (1, True)),
    ({"type": "cost-state", "totalCostUsd": "x"}, None),
    ({"type": "assistant", "totalCostUsd": 9.0}, None),
    ({"type": "cost-state"}, None),
])
def test_cost_state_reads_the_adapter_field(entry, want):
    assert lib.cost_state(entry) == want


def test_cost_py_names_no_harness_field():
    src = (lib.__file__ and open(lib.__file__.replace("reflectlib.py", "cost.py")).read())
    assert "cost-state" not in src and "totalCostU" not in src
