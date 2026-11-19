"""Tests for hooks/secret-read-guard. Run: python3 -m pytest hooks/tests
All values are obvious dummies; no test reads a real file."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "secret-read-guard")
_loader = importlib.machinery.SourceFileLoader("secret_read_guard", HOOK)
_spec = importlib.util.spec_from_loader("secret_read_guard", _loader)
srg = importlib.util.module_from_spec(_spec)
_loader.exec_module(srg)

ASK = [
    "cat .env",
    "cat .env.local",
    "cat prod.env",
    "less ~/.ssh/id_ed25519",
    "head -5 /home/u/.ssh/id_rsa",
    "tail -n 3 vault.kdbx",
    "cat talosconfig",
    "cat ~/.kube/config",
    "cat kubeconfig",
    "cat server.pem",
    "cat credentials.json",
    "cat ~/.netrc",
    "cat ~/.aws/credentials",
    "grep password ~/.aws/credentials",
    "grep -n token .env",
    "sed -n 1,5p .env",
    "cat ~/Library/Caches/KeePassXC/keepassxc.ini",
    "cat < .env",
    "cat .env | head",
    "cat .env 2>/dev/null",
    "cat .env | grep -v '^#'",
    "bash -c 'cat .env'",
    "sh -c \"cat ~/.netrc\"",
    "bash -lc 'echo hi; cat .env'",
    "eval 'cat .env'",
    "sudo cat .env",
    "FOO=1 cat .env",
    "ls && cat .env",
    "true; cat .env",
    "echo $(cat .env)",
    "env",
    "env | sort",
    "env | grep TOKEN",
    "printenv",
    "set",
    "export -p",
    "declare -p",
    "printenv GITHUB_TOKEN",
    "echo $GITHUB_TOKEN",
    'echo "$API_SECRET"',
    "echo ${DB_PASSWORD}",
    "printf '%s' $AWS_SECRET_ACCESS_KEY",
    "security find-generic-password -s foo -w",
    "security find-internet-password -a me -gw",
    "security find-generic-password -w x",
    "keepassxc-cli show -s db.kdbx entry",
    "cat <<EOF\nhello\nEOF\ncat .env",
]

ALLOW = [
    "cat README.md",
    "ls ~/.ssh",
    "echo $HOME",
    "echo $PATH",
    "printenv PATH",
    "printenv HOME USER",
    "env FOO=1 ls",
    "set -e",
    "cat .env.example",
    "cat ~/.ssh/id_ed25519.pub",
    "cat .envrc.md",
    "grep -l token .env",
    "grep -c token .env",
    "grep -q TOKEN .env",
    "grep --count TOKEN .env",
    "grep --files-with-matches TOKEN .env",
    "wc -l .env",
    "test -f .env",
    "[ -f ~/.netrc ]",
    "stat ~/.ssh/id_rsa",
    "cut -d= -f1 .env",
    "cat .env | wc -l",
    "cat .env | grep -c TOKEN",
    "cat .env | cut -d= -f1",
    "cat .env | pbcopy",
    "cat .env > /tmp/copy",
    "cat .env >> /tmp/copy",
    "env | grep -c TOKEN",
    "env | wc -l",
    "env | cut -d= -f1",
    "printenv | wc -l",
    "echo $GITHUB_TOKEN | pbcopy",
    "echo ${#GITHUB_TOKEN}",
    "echo $SSH_KEY_FILE",
    "echo ${GITHUB_TOKEN:+set}",
    "security find-generic-password -s foo",
    "security find-generic-password -w x | pbcopy",
    "security add-generic-password -a me -s foo",
    "security find-identity -v",
    "keepassxc-cli show db.kdbx entry",
    "grep -r '.env' src",
    "git commit -m 'cat .env'",
    "echo 'cat .env'",
    "cat <<EOF\ncat .env\nEOF",
    "cat <<'EOF' > notes.txt\nenv\nEOF",
    "bash -c 'ls ~/.ssh'",
    "bash script.sh",
    "",
    "   ",
]


class BashTable(unittest.TestCase):
    def test_ask(self):
        for cmd in ASK:
            with self.subTest(cmd=cmd):
                self.assertTrue(srg.bash_reason(cmd), cmd)

    def test_allow(self):
        for cmd in ALLOW:
            with self.subTest(cmd=cmd):
                self.assertEqual(srg.bash_reason(cmd), "")

    def test_reason_names_safe_alternative(self):
        reason = srg.bash_reason("cat .env")
        self.assertIn("show-config", reason)
        self.assertIn("grep -c", reason)
        self.assertIn("cut -d= -f1", reason)

    def test_malformed_and_odd_input_does_not_raise(self):
        for cmd in ["cat 'unterminated .env", 'echo "open', "cat <<", "cat <<EOF\nnever ends", "&&&|||;;;", "\x00", "(((",
                    None, 7, ["cat", ".env"]]:
            with self.subTest(cmd=cmd):
                srg.bash_reason(cmd)

    def test_deep_bash_c_nesting_terminates(self):
        cmd = "cat .env"
        for _ in range(10):
            cmd = "bash -c " + json.dumps(cmd)
        srg.bash_reason(cmd)

    def test_long_input_is_linear(self):
        for cmd in ["cat " + "a " * 200_000, "echo " + "$" * 200_000, "cat " + "'" * 200_000, "x;" * 200_000]:
            srg.bash_reason(cmd)


class ReadTable(unittest.TestCase):
    def test_ask(self):
        for path in ["/p/.env", "/p/.env.production", "/h/.ssh/id_ed25519", "/h/db.kdbx",
                     "/h/.aws/credentials", "/p/talosconfig", "/h/.netrc", "/h/x.pem"]:
            with self.subTest(path=path):
                self.assertTrue(srg.read_reason(path))

    def test_allow(self):
        for path in ["/p/README.md", "/h/.ssh/id_ed25519.pub", "/h/.ssh/config",
                     "/p/.env.example", "/p/src/main.rs", "", None, 3]:
            with self.subTest(path=path):
                self.assertEqual(srg.read_reason(path), "")


EXTRA = "~/.config/vault/*/*:/srv/secrets/*"


class ExtraPaths(unittest.TestCase):
    """Site-specific protected paths come from AGENT_GUARDRAILS_SECRET_PATHS, never from the script."""

    def setUp(self):
        self._saved = os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)

    def tearDown(self):
        os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)
        if self._saved is not None:
            os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = self._saved

    def test_no_site_rule_without_config(self):
        for path in ["/h/.config/site/org/token", "/h/.config/vault/org/token", "/srv/secrets/db"]:
            with self.subTest(path=path):
                self.assertEqual(srg.read_reason(path), "")
        self.assertEqual(srg.bash_reason("cat ~/.config/site/org/token"), "")

    def test_configured_globs_are_protected(self):
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = EXTRA
        home = os.path.expanduser("~")
        for path in [home + "/.config/vault/org/token", "/srv/secrets/db"]:
            with self.subTest(path=path):
                self.assertTrue(srg.read_reason(path))
        for cmd in ["cat ~/.config/vault/org/token", "cat $HOME/.config/vault/org/token",
                    "cat ${HOME}/.config/vault/org/token", "cat /srv/secrets/db", "grep x /srv/secrets/db"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(srg.bash_reason(cmd))

    def test_configured_globs_leave_other_paths_and_listings_alone(self):
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = EXTRA
        for cmd in ["ls ~/.config/vault/org", "cat ~/.config/other/x", "grep -l x /srv/secrets/db",
                    "cat /srv/secretsx/db"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(srg.bash_reason(cmd), "")

    def test_empty_entries_and_empty_config_are_ignored(self):
        for value in ["", ":", "::", ":/srv/secrets/*:"]:
            os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = value
            self.assertEqual(srg.read_reason("/p/README.md"), "")

    def test_dotdot_segments_are_resolved_before_matching(self):
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = "/srv/secrets/*"
        self.assertTrue(srg.bash_reason("cat /srv/x/../secrets/db"))
        self.assertTrue(srg.read_reason("/srv/x/../secrets/db"))
        self.assertEqual(srg.bash_reason("cat /srv/x/db"), "")

    def test_relative_paths_resolve_against_the_payload_cwd(self):
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = "/srv/secrets/*"
        self.assertTrue(srg.read_reason("db", cwd="/srv/secrets"))
        self.assertTrue(srg.read_reason("../secrets/db", cwd="/srv/x"))
        self.assertTrue(srg.bash_reason("cat db", cwd="/srv/secrets"))
        self.assertEqual(srg.read_reason("db", cwd="/srv/other"), "")

    def test_cd_earlier_in_the_command_moves_the_working_directory(self):
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = "/srv/secrets/*"
        self.assertTrue(srg.bash_reason("cd /srv/secrets && cat db"))
        self.assertTrue(srg.bash_reason("cd /srv; cd secrets; cat db"))
        self.assertTrue(srg.bash_reason("cd /srv && bash -c 'cd secrets && cat db'"))
        self.assertEqual(srg.bash_reason("cd /srv/other && cat db"), "")

    def test_user_home_forms_are_expanded(self):
        root = os.path.expanduser("~root")
        if root == "~root":
            self.skipTest("no root user home")
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = root + "/vault/*"
        self.assertTrue(srg.bash_reason("cat ~root/vault/tok"))

    def test_case_variants_match_only_on_a_case_insensitive_filesystem(self):
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = "/srv/secrets/*"
        saved = srg.CASE_INSENSITIVE
        try:
            srg.CASE_INSENSITIVE = True
            self.assertTrue(srg.read_reason("/SRV/Secrets/DB"))
            srg.CASE_INSENSITIVE = False
            self.assertEqual(srg.read_reason("/SRV/Secrets/DB"), "")
        finally:
            srg.CASE_INSENSITIVE = saved

    def test_case_default_follows_the_platform(self):
        self.assertEqual(srg.CASE_INSENSITIVE, sys.platform in ("darwin", "win32"))

    def test_hook_process_resolves_a_relative_read_against_the_payload_cwd(self):
        env = {**os.environ, "AGENT_GUARDRAILS_SECRET_PATHS": "/srv/secrets/*"}
        rc, out = run_hook({"tool_name": "Read", "cwd": "/srv/secrets", "tool_input": {"file_path": "db"}}, env=env)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_hook_process_reads_the_env(self):
        env = {**os.environ, "AGENT_GUARDRAILS_SECRET_PATHS": EXTRA}
        rc, out = run_hook({"tool_name": "Read", "tool_input": {"file_path": "/srv/secrets/db"}}, env=env)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")


def run_hook(payload, env=None):
    r = subprocess.run([sys.executable, HOOK], input=payload if isinstance(payload, str) else json.dumps(payload),
                       capture_output=True, text=True, timeout=20, env=env)
    return r.returncode, r.stdout


class EndToEnd(unittest.TestCase):
    def decision(self, payload):
        rc, out = run_hook(payload)
        self.assertEqual(rc, 0)
        return json.loads(out)["hookSpecificOutput"] if out.strip() else None

    def test_bash_ask_is_ask_not_deny(self):
        out = self.decision({"tool_name": "Bash", "tool_input": {"command": "cat .env"}})
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertIn("show-config", out["permissionDecisionReason"])

    def test_read_ask(self):
        out = self.decision({"tool_name": "Read", "tool_input": {"file_path": "/p/.env"}})
        self.assertEqual(out["permissionDecision"], "ask")

    def test_clean_calls_silent(self):
        self.assertIsNone(self.decision({"tool_name": "Bash", "tool_input": {"command": "cat README.md"}}))
        self.assertIsNone(self.decision({"tool_name": "Read", "tool_input": {"file_path": "/p/README.md"}}))

    def test_other_tools_and_malformed_fail_open(self):
        self.assertIsNone(self.decision({"tool_name": "Edit", "tool_input": {"file_path": "/p/.env"}}))
        for bad in ["", "not json", "[]", "null", json.dumps({"tool_name": "Bash"}),
                    json.dumps({"tool_name": "Bash", "tool_input": "cat .env"}),
                    json.dumps({"tool_name": "Bash", "tool_input": {"command": 5}})]:
            with self.subTest(bad=bad):
                self.assertIsNone(self.decision(bad))


if __name__ == "__main__":
    unittest.main()
