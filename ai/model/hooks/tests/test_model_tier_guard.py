"""Tests for hooks/model-tier-guard.py. Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model-tier-guard.py")


def run_hook(payload=None, raw=None, env=None):
    return subprocess.run(
        [sys.executable, HOOK],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True, text=True, timeout=20,
        env={**os.environ, "AGENT_HARNESS": "claude", **(env or {})},
    )


def agent(**tool_input):
    return {"tool_name": "Agent", "tool_input": {"prompt": "p", "description": "d", **tool_input}}


class Helpers:
    def assert_denied(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("haiku", out["permissionDecisionReason"])
        self.assertIn("sonnet", out["permissionDecisionReason"])

    def assert_allowed(self, r):
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def assert_defaulted(self, r, model):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)  # E2: an allow would skip the user's permission rules
        self.assertIn(model, out["additionalContext"])
        self.assertEqual(out["updatedInput"]["model"], model)
        # updatedInput replaces the whole input: prompt and description must survive.
        self.assertEqual((out["updatedInput"]["prompt"], out["updatedInput"]["description"]), ("p", "d"))


    def assert_denied_for(self, r, *needles):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        for needle in needles:
            self.assertIn(needle, out["permissionDecisionReason"])


class AgentModelGuard(Helpers, unittest.TestCase):
    def test_missing_model_denied(self):
        self.assert_denied(run_hook(agent(subagent_type="general-purpose")))

    def test_e2_models_the_tool_accepts_pass_through_unchanged(self):
        for model in ("fable", "claude-opus-4-1-20250805", "claude-sonnet-4-5"):
            with self.subTest(model=model):
                self.assert_allowed(run_hook(agent(subagent_type="general-purpose", model=model)))

    def test_e2_tier_typos_are_still_denied(self):
        for model in ("gpt", "sonet", "Light", "reasonning", ""):
            with self.subTest(model=model):
                self.assert_denied(run_hook(agent(subagent_type="general-purpose", model=model)))

    def test_unknown_model_denied(self):
        self.assert_denied(run_hook(agent(subagent_type="general-purpose", model="gpt")))

    def test_review_only_without_model_denied(self):
        self.assert_denied(run_hook(agent(subagent_type="review-only")))

    def test_sonnet_and_haiku_allowed(self):
        for model in ("sonnet", "haiku"):
            with self.subTest(model=model):
                self.assert_allowed(run_hook(agent(subagent_type="general-purpose", model=model)))

    def test_opus_general_purpose_without_reasoning_reason_denied(self):
        for st in ("general-purpose", None):
            with self.subTest(subagent_type=st):
                kw = {"subagent_type": st} if st else {}
                self.assert_denied_for(run_hook(agent(model="opus", description="Implement the parser", **kw)),
                                       "sonnet", "reasoning")

    def test_opus_allowed_with_reasoning_tier_reason_in_description_or_prompt(self):
        for text in ("Architecture review of the cache", "Design the retry layer", "Adversarial review of the diff",
                     "Novel debugging: hang only in CI", "root cause of the deadlock"):
            with self.subTest(text=text):
                self.assert_allowed(run_hook(agent(subagent_type="general-purpose", model="opus", description=text)))
                self.assert_allowed(run_hook(agent(subagent_type="general-purpose", model="opus", description="x",
                                                   prompt=f"Task: {text}")))

    def test_opus_for_other_types_untouched(self):
        for st in ("Plan", "review-only", "code-simplifier"):
            with self.subTest(subagent_type=st):
                self.assert_allowed(run_hook(agent(subagent_type=st, model="opus")))

    def test_search_only_prompt_on_readonly_agent_needs_haiku(self):
        prompt = "Find all callers of parse_config and list the files where it is defined."
        for st in ("Explore", "review-only", "explore-helper", "Read-Only Scout"):
            for model in ("sonnet", "opus"):
                with self.subTest(subagent_type=st, model=model):
                    self.assert_denied_for(run_hook(agent(subagent_type=st, model=model, prompt=prompt)), "haiku")
            with self.subTest(subagent_type=st, model="haiku"):
                self.assert_allowed(run_hook(agent(subagent_type=st, model="haiku", prompt=prompt)))

    def test_non_search_prompts_on_readonly_agent_keep_their_model(self):
        for prompt in ("Review this diff adversarially and find the bugs.",
                       "Find the callers of parse_config, then analyze why the lock order is wrong.",
                       "Audit the module and explain the design.",
                       "Summarise the module",
                       "x" * 2000 + " find the file"):
            with self.subTest(prompt=prompt[:40]):
                self.assert_allowed(run_hook(agent(subagent_type="review-only", model="sonnet", prompt=prompt)))

    def test_search_only_prompt_on_general_purpose_not_denied(self):
        self.assert_allowed(run_hook(agent(subagent_type="general-purpose", model="sonnet",
                                           prompt="Find all callers of parse_config.")))

    def test_fork_with_opus_and_search_prompt_still_exempt(self):
        self.assert_allowed(run_hook(agent(subagent_type="fork", model="opus", prompt="Find the file.")))

    def test_known_readonly_agent_defaults_to_haiku(self):
        for subagent_type in ("Explore", "claude-code-guide", "statusline-setup"):
            with self.subTest(subagent_type=subagent_type):
                self.assert_defaulted(run_hook(agent(subagent_type=subagent_type)), "haiku")

    def test_known_readonly_agent_explicit_model_wins(self):
        self.assert_allowed(run_hook(agent(subagent_type="Explore", model="sonnet")))

    def test_fork_exempt(self):
        # A fork always runs on the parent model; a model override is ignored.
        self.assert_allowed(run_hook(agent(subagent_type="fork")))

    def test_other_tool_ignored(self):
        self.assert_allowed(run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}))

    def test_malformed_input_fails_open(self):
        for raw in ("", "not json", "[]", '{"tool_name":"Agent"}'):
            with self.subTest(raw=raw):
                self.assert_allowed(run_hook(raw=raw))


class TierNames(Helpers, unittest.TestCase):
    """The model argument may also name a tier; the tier map (tiers.json) turns it into the harness model."""

    def assert_resolved(self, r, model):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)
        self.assertIn(model, out["additionalContext"])
        self.assertEqual(out["updatedInput"]["model"], model)
        self.assertIn("prompt", out["updatedInput"])  # updatedInput replaces the whole input
        self.assertIn("description", out["updatedInput"])

    def test_tier_names_resolve_through_the_map(self):
        for tier, model in (("light", "haiku"), ("execution", "sonnet")):
            with self.subTest(tier=tier):
                self.assert_resolved(run_hook(agent(subagent_type="general-purpose", model=tier)), model)

    def test_reasoning_tier_resolves_with_a_reasoning_reason(self):
        self.assert_resolved(run_hook(agent(subagent_type="general-purpose", model="reasoning",
                                            description="Design the retry layer")), "opus")

    def test_reasoning_tier_without_reason_denied_like_opus(self):
        r = run_hook(agent(subagent_type="general-purpose", model="reasoning", description="Implement the parser"))
        self.assert_denied_for(r, "sonnet", "reasoning")

    def test_light_tier_satisfies_the_search_only_rule(self):
        prompt = "Find all callers of parse_config and list the files where it is defined."
        self.assert_resolved(run_hook(agent(subagent_type="Explore", model="light", prompt=prompt)), "haiku")
        self.assert_denied_for(run_hook(agent(subagent_type="Explore", model="execution", prompt=prompt)), "light")

    def test_fork_with_tier_name_still_exempt(self):
        self.assert_allowed(run_hook(agent(subagent_type="fork", model="reasoning")))


class MapDrivesTheHook(Helpers, unittest.TestCase):
    """No model name is hardcoded: another map gives another vocabulary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def tiers(self, **harness_models):
        path = os.path.join(self.tmp.name, "tiers.json")
        with open(path, "w") as f:
            json.dump({"tiers": {t: {"claude": m, "codex": "TODO"} for t, m in harness_models.items()}}, f)
        return path

    def test_custom_models_are_allowed_and_claude_names_are_not(self):
        env = {"AGENT_TIERS_FILE": self.tiers(light="mini", execution="mid", reasoning="max")}
        self.assertEqual(run_hook(agent(subagent_type="general-purpose", model="mid"), env=env).stdout, "")
        r = run_hook(agent(subagent_type="general-purpose", model="sonnet"), env=env)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("mini", out["permissionDecisionReason"])
        self.assertNotIn("haiku", out["permissionDecisionReason"])

    def test_custom_map_drives_defaults_and_tier_resolution(self):
        env = {"AGENT_TIERS_FILE": self.tiers(light="mini", execution="mid", reasoning="max")}
        out = json.loads(run_hook(agent(subagent_type="Explore"), env=env).stdout)["hookSpecificOutput"]
        self.assertEqual(out["updatedInput"]["model"], "mini")
        out = json.loads(run_hook(agent(subagent_type="general-purpose", model="execution"), env=env).stdout)
        self.assertEqual(out["hookSpecificOutput"]["updatedInput"]["model"], "mid")

    def test_custom_light_model_enforces_the_search_rule(self):
        env = {"AGENT_TIERS_FILE": self.tiers(light="mini", execution="mid", reasoning="max")}
        prompt = "Find all callers of parse_config."
        r = run_hook(agent(subagent_type="Explore", model="mid", prompt=prompt), env=env)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(run_hook(agent(subagent_type="Explore", model="mini", prompt=prompt), env=env).stdout, "")

    def note(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertNotIn("\n", out["additionalContext"])
        return out["additionalContext"]

    def test_placeholder_harness_fails_open_and_says_so(self):
        # codex values are TODO in the shipped map: nothing to resolve, so the hook must not guess.
        for payload in (agent(subagent_type="general-purpose"), agent(subagent_type="Explore"),
                        agent(subagent_type="general-purpose", model="light")):
            with self.subTest(payload=payload):
                ctx = self.note(run_hook(payload, env={"AGENT_HARNESS": "codex"}))
                self.assertIn("codex", ctx)

    def test_missing_or_broken_map_fails_open_and_says_so(self):
        path = os.path.join(self.tmp.name, "broken.json")
        with open(path, "w") as f:
            f.write("{")
        for env in ({"AGENT_TIERS_FILE": path}, {"AGENT_TIERS_FILE": os.path.join(self.tmp.name, "absent.json")}):
            with self.subTest(env=env):
                ctx = self.note(run_hook(agent(subagent_type="general-purpose"), env=env))
                self.assertIn(env["AGENT_TIERS_FILE"], ctx)

    def test_fork_and_other_tools_stay_silent_even_with_a_broken_map(self):
        env = {"AGENT_TIERS_FILE": os.path.join(self.tmp.name, "absent.json")}
        self.assertEqual(run_hook(agent(subagent_type="fork"), env=env).stdout, "")
        self.assertEqual(run_hook({"tool_name": "Bash", "tool_input": {}}, env=env).stdout, "")

    def raw_map(self, tiers):
        path = os.path.join(self.tmp.name, "raw.json")
        with open(path, "w") as f:
            json.dump({"tiers": tiers}, f)
        return {"AGENT_TIERS_FILE": path}

    def test_d1_a_tier_without_the_harness_key_is_only_that_tier_absent(self):
        env = self.raw_map({"light": {"claude": "haiku"}, "execution": {"claude": "sonnet"},
                            "reasoning": {"claude": "opus"}, "speed": {"codex": "x"}})
        self.assert_denied(run_hook(agent(subagent_type="general-purpose"), env=env))

    def test_d1_a_tier_missing_the_harness_key_does_not_disable_the_others(self):
        env = self.raw_map({"light": {"codex": "x"}, "execution": {"claude": "sonnet"}})
        r = run_hook(agent(subagent_type="general-purpose"), env=env)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_d2_built_in_defaults_survive_a_map_without_a_light_tier(self):
        for tiers in ({"light": {"claude": "TODO"}, "execution": {"claude": "sonnet"}},
                      {"execution": {"claude": "sonnet"}}):
            with self.subTest(tiers=tiers):
                for st in ("Explore", "claude-code-guide", "statusline-setup"):
                    self.assert_defaulted(run_hook(agent(subagent_type=st), env=self.raw_map(tiers)), "haiku")

    def test_d3_tier_keys_are_a_fixed_set_and_model_names_are_never_remapped(self):
        env = self.raw_map({"haiku": {"claude": "sonnet"}, "light": {"claude": "haiku"},
                            "execution": {"claude": "sonnet"}, "reasoning": {"claude": "opus"}})
        r = run_hook(agent(subagent_type="general-purpose", model="haiku"), env=env)
        self.assertEqual((r.returncode, r.stdout), (0, ""))  # allowed as is, not rewritten to sonnet

    def test_d3_a_map_without_reasoning_still_gates_opus(self):
        env = self.raw_map({"light": {"claude": "haiku"}, "execution": {"claude": "sonnet"}})
        self.assert_denied_for(run_hook(agent(subagent_type="general-purpose", model="opus",
                                              description="Implement the parser"), env=env), "reasoning")
        self.assert_allowed(run_hook(agent(subagent_type="general-purpose", model="opus",
                                           description="Design the retry layer"), env=env))

    def test_d4_own_agents_default_to_their_tier(self):
        for st, model in (("reader", "haiku"), ("builder", "sonnet"), ("reasoner", "opus"),
                          ("models:reader", "haiku"), ("models:builder", "sonnet"),
                          ("models:reasoner", "opus")):
            with self.subTest(subagent_type=st):
                self.assert_defaulted(run_hook(agent(subagent_type=st)), model)

    def test_d4_other_plugins_agents_are_not_ours(self):
        self.assert_denied(run_hook(agent(subagent_type="other:reader")))


    def test_shipped_map_has_the_three_tiers_for_claude(self):
        path = os.path.join(os.path.dirname(HOOK), "..", "tiers.json")
        with open(path) as f:
            tiers = json.load(f)["tiers"]
        self.assertEqual({t: tiers[t]["claude"] for t in tiers},
                         {"light": "haiku", "execution": "sonnet", "reasoning": "opus"})


class AgentFiles(unittest.TestCase):
    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "agents")
    CLAUDE_TOOLS = {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "MultiEdit"}

    def meta(self, name):
        with open(os.path.join(self.ROOT, name + ".md")) as f:
            head = f.read().split("---")[1]
        return dict(line.split(":", 1) for line in head.strip().splitlines() if ":" in line)

    def tools(self, name):
        return {t.strip() for t in self.meta(name)["tools"].strip().split(",")}

    def test_tiers_and_claude_native_tools(self):
        for name, tier in (("reader", "light"), ("builder", "execution"), ("reasoner", "reasoning")):
            with self.subTest(agent=name):
                self.assertEqual(self.meta(name)["tier"].strip(), tier)
                self.assertTrue(self.tools(name) <= self.CLAUDE_TOOLS, self.tools(name))

    def test_roles_match_their_claims(self):
        writers = {"Bash", "Edit", "Write", "MultiEdit"}
        self.assertEqual(self.tools("reader") & writers, set())
        self.assertEqual(self.tools("reasoner") & writers, set())
        self.assertTrue({"Edit", "Write", "Bash"} <= self.tools("builder"))


if __name__ == "__main__":
    unittest.main()
