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


class BuiltInRulesResolveAgainstCwd(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)

    def test_cd_into_the_secret_directory_then_read_a_bare_name(self):
        for cmd in ["cd ~/.ssh && cat id_rsa", "cd $HOME/.ssh; cat id_ed25519", "cd ~/.kube && cat config",
                    "cd ~/Library/Caches && cat KeePassXC/keepassxc.ini"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(srg.bash_reason(cmd))

    def test_payload_cwd_inside_a_secret_directory(self):
        home = os.path.expanduser("~")
        self.assertTrue(srg.read_reason("id_rsa", cwd=home + "/.ssh"))
        self.assertTrue(srg.bash_reason("cat config", cwd=home + "/.kube"))
        self.assertEqual(srg.read_reason("id_rsa.pub", cwd=home + "/.ssh"), "")
        self.assertEqual(srg.read_reason("id_rsa", cwd="/work/project"), "")

    def test_dotdot_into_a_secret_directory(self):
        self.assertTrue(srg.bash_reason("cat ~/x/../.ssh/id_rsa"))


class CompoundShapesAndWrappers(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)

    def test_keywords_and_braces_are_not_the_command(self):
        for cmd in ["for f in .env; do cat .env; done", "if true; then cat .env; fi", "{ cat .env; }",
                    "while true; do cat .env; done", "! cat .env", "if cat .env; then echo hi; fi",
                    "true && { cat .env; }", "if true\nthen\n  cat .env\nfi"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(srg.bash_reason(cmd))

    def test_wrappers_with_flags_leave_the_real_command(self):
        for cmd in ["nice -n 5 cat .env", "env -u X cat .env", "env --unset X cat .env", "env -i FOO=1 cat .env",
                    "timeout 60 cat .env", "timeout -s KILL 5 cat .env", "sudo -u root cat .env",
                    "stdbuf -o L cat .env", "xargs -n 1 cat < .env", "command -p cat .env", "builtin echo $API_TOKEN",
                    "ionice -c 3 cat .env", "setsid cat .env", "exec cat .env", "nohup cat .env", "time cat .env",
                    "sudo env -u X cat .env", "nice -n 5 timeout 9 cat .env"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(srg.bash_reason(cmd))

    def test_wrapper_arguments_are_not_taken_for_the_command(self):
        for cmd in ["nice -n 5 ls", "env -u TOKEN ls .env.example", "timeout 60 ls", "sudo -u cat ls"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(srg.bash_reason(cmd), "")


class Heredocs(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)

    def test_quoted_heredoc_marker_does_not_swallow_later_lines(self):
        self.assertTrue(srg.bash_reason("echo '<<EOF'\ncat .env\nEOF"))
        self.assertTrue(srg.bash_reason('echo "a << b"\ncat .env'))
        self.assertTrue(srg.bash_reason("echo x # not <<EOF\ncat .env"))

    def test_multiline_quoted_string_does_not_start_a_heredoc(self):
        self.assertTrue(srg.bash_reason("echo 'first\n<<EOF'\ncat .env"))

    def test_real_heredoc_body_is_still_data_for_a_non_shell_consumer(self):
        self.assertEqual(srg.bash_reason("cat <<EOF\ncat .env\nEOF"), "")
        self.assertEqual(srg.bash_reason("cat <<'EOF' > out.txt\ncat .env\nEOF"), "")
        self.assertEqual(srg.bash_reason("python3 - <<EOF\nprint(1)\nEOF"), "")

    def test_body_fed_to_a_shell_is_scanned(self):
        for cmd in ["cat <<'EOF' | bash\ncat .env\nEOF", "cat <<EOF | sh\ncat .env\nEOF", "bash <<EOF\ncat .env\nEOF",
                    "sh -s <<EOF\ncat .env\nEOF", "sudo bash <<'EOF'\ncat .env\nEOF", "bash -s -- <<EOF\ncat .env\nEOF",
                    "zsh <<EOF\ncat .env\nEOF"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(srg.bash_reason(cmd))

    def test_commands_after_the_terminator_are_scanned_as_before(self):
        self.assertTrue(srg.bash_reason("cat <<EOF\nhi\nEOF\ncat .env"))


class SafeBasenames(unittest.TestCase):
    """Files that carry no secrets (ssh_config) pass even inside a configured protected directory."""

    def setUp(self):
        self._saved = os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)
        os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = "$HOME/.config/site/*/*"
        self.d = "~/.config/site/org"

    def tearDown(self):
        os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)
        if self._saved is not None:
            os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = self._saved

    def test_ssh_config_passes_in_read_cat_head_grep_redirect_and_heredoc_forms(self):
        home = os.path.expanduser("~")
        self.assertEqual(srg.read_reason(home + "/.config/site/org/ssh_config"), "")
        for cmd in ["cat %s/ssh_config", "head -5 %s/ssh_config", "cat < %s/ssh_config", "grep Host %s/ssh_config",
                    "rg -n Host %s/ssh_config", "cat $HOME/.config/site/org/ssh_config",
                    "cd %s && cat ssh_config", "bash -c 'cat %s/ssh_config'", "cat %s/ssh_config > /dev/null",
                    "cat <<EOF\nx\nEOF\ncat %s/ssh_config"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(srg.bash_reason(cmd.replace("%s", self.d) if "%s" in cmd else cmd), "")

    def test_grep_tool_over_ssh_config_passes(self):
        home = os.path.expanduser("~")
        self.assertEqual(srg.grep_reason({"output_mode": "content", "pattern": "Host",
                                          "path": home + "/.config/site/org/ssh_config"}), "")
        self.assertTrue(srg.grep_reason({"output_mode": "content", "pattern": "x",
                                         "path": home + "/.config/site/org/kubeconfig"}))

    def test_other_names_in_the_directory_stay_guarded(self):
        for name in ["ssh_config_backup", "ssh_config.bak", "ssh_config2", "kubeconfig", "talosconfig", "token",
                     "vpn.key", "SSH_CONFIG.d"]:
            with self.subTest(name=name):
                self.assertTrue(srg.read_reason("~/.config/site/org/" + name))
                self.assertTrue(srg.bash_reason("cat ~/.config/site/org/" + name))

    def test_dotdot_traversal_cannot_reach_a_secret_through_ssh_config(self):
        for path in ["~/.config/site/org/ssh_config/../token", "~/.config/site/org/../org/token",
                     "~/.config/site/org/x/../kubeconfig"]:
            with self.subTest(path=path):
                self.assertTrue(srg.read_reason(path))
                self.assertTrue(srg.bash_reason("cat " + path))

    def test_cd_into_the_directory_does_not_exempt_other_files(self):
        self.assertTrue(srg.bash_reason("cd ~/.config/site/org && cat kubeconfig"))
        self.assertTrue(srg.bash_reason("cd ~/.config/site/org && cat ssh_config kubeconfig"))

    def test_symlink_named_ssh_config_to_a_secret_stays_guarded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            org = os.path.join(root, "site", "org")
            os.makedirs(org)
            secret = os.path.join(org, "token")
            open(secret, "w").close()
            link = os.path.join(org, "ssh_config")
            os.symlink(secret, link)
            os.environ["AGENT_GUARDRAILS_SECRET_PATHS"] = os.path.realpath(root) + "/site/*/*"
            self.assertTrue(srg.read_reason(link))
            self.assertTrue(srg.bash_reason("cat " + link))
            os.unlink(link)
            open(link, "w").close()  # a regular ssh_config
            self.assertEqual(srg.read_reason(link), "")

    def test_builtin_rules_still_apply_to_the_safe_name(self):
        self.assertTrue(srg.read_reason("/p/.env"))
        self.assertTrue(srg.read_reason("/p/kubeconfig"))

    def test_hook_process_lets_ssh_config_through(self):
        env = {**os.environ}
        for tool, ti in [("Read", {"file_path": "~/.config/site/org/ssh_config"}),
                         ("Bash", {"command": "cat ~/.config/site/org/ssh_config"})]:
            rc, out = run_hook({"tool_name": tool, "tool_input": ti}, env=env)
            self.assertEqual((rc, out.strip()), (0, ""), tool)
        rc, out = run_hook({"tool_name": "Read", "tool_input": {"file_path": "~/.config/site/org/token"}}, env=env)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")


class GrepTool(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AGENT_GUARDRAILS_SECRET_PATHS", None)

    def ask(self, **tool_input):
        rc, out = run_hook({"tool_name": "Grep", "tool_input": {"pattern": "x", **tool_input}})
        self.assertEqual(rc, 0)
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip() else None

    def test_content_mode_over_a_secret_file_asks(self):
        self.assertEqual(self.ask(path="/p/.env", output_mode="content"), "ask")
        self.assertEqual(self.ask(path="/h/.ssh/id_rsa", output_mode="content"), "ask")

    def test_content_mode_with_a_secret_glob_asks(self):
        for glob in (".env*", "*.env", "**/*.pem", "*.kdbx", "credentials*", "**/.netrc"):
            with self.subTest(glob=glob):
                self.assertEqual(self.ask(glob=glob, output_mode="content"), "ask")

    def test_listing_modes_and_ordinary_paths_pass(self):
        self.assertIsNone(self.ask(path="/p/.env", output_mode="files_with_matches"))
        self.assertIsNone(self.ask(path="/p/.env", output_mode="count"))
        self.assertIsNone(self.ask(path="/p/.env"))  # default mode lists files
        self.assertIsNone(self.ask(path="/p/src", output_mode="content"))
        self.assertIsNone(self.ask(glob="*.rs", output_mode="content"))

    def test_manifest_registers_grep_with_a_raw_claude_matcher(self):
        with open(os.path.join(os.path.dirname(HOOK), "manifest.json")) as f:
            entries = json.load(f)["hooks"]
        grep = [e for e in entries if e["script"] == "hooks/secret-read-guard" and e.get("matcher") == "Grep"]
        self.assertEqual(len(grep), 1)
        with open(os.path.join(os.path.dirname(HOOK), "..", "README.md")) as f:
            self.assertIn("Claude Code only", f.read())


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
