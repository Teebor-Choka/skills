"""Table-driven tests for hooks/git-guard. Run: python3 -m unittest discover -s hooks/tests -v"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "git-guard")
_loader = importlib.machinery.SourceFileLoader("git_guard", HOOK)
_spec = importlib.util.spec_from_loader("git_guard", _loader)
guard = importlib.util.module_from_spec(_spec)
_loader.exec_module(guard)

DENY, ASK, ALLOW = "deny", "ask", "allow"

# (command, branch the fake resolver reports, expected decision)
CASES = [
    # deny: blanket staging
    ("git add -A", "feat", DENY),
    ("git add --all", "feat", DENY),
    ("git add .", "feat", DENY),
    ("git add ./", "feat", DENY),
    ("git add -- .", "feat", DENY),
    ("git add -Av", "feat", DENY),
    ("git add src/a.rs .", "feat", DENY),
    ("git add -N .", "feat", DENY),
    ("git -C /repo add -A", "feat", DENY),
    ("git -c core.x=1 add .", "feat", DENY),
    ("cd /repo && git add .", "feat", DENY),
    ("git status; git add -A", "feat", DENY),
    ("FOO=1 git add -A", "feat", DENY),
    ("env FOO=1 git add -A", "feat", DENY),
    ('bash -c "git add -A"', "feat", DENY),
    ("echo $(git add -A)", "feat", DENY),
    # allow: explicit staging
    ("git add src/a.rs", "feat", ALLOW),
    ("git add -u", "feat", ALLOW),
    ("git add -p", "feat", ALLOW),
    ("git add .gitignore", "feat", ALLOW),
    ("git add -- src/a.rs", "feat", ALLOW),
    ("git add hooks/ settings.json", "feat", ALLOW),
    ("git add -N hosts/web01.nix flake.nix", "feat", ALLOW),
    # ask: merges
    ("gh pr merge 12", "feat", ASK),
    ("gh pr merge --squash --delete-branch", "feat", ASK),
    ("gh pr merge 12 -R o/r", "feat", ASK),
    ("gh -R o/r pr merge 12", "feat", ASK),
    ("gh api -X PUT repos/o/r/pulls/3/merge", "feat", ASK),
    ("cd /x && gh pr merge 1", "feat", ASK),
    # allow: other gh
    ("gh pr create --draft --title t", "feat", ALLOW),
    ("gh pr view 3", "feat", ALLOW),
    ("gh pr list", "feat", ALLOW),
    ("gh api repos/o/r/pulls/3", "feat", ALLOW),
    # ask: pushes to protected branches
    ("git push origin main", "feat", ASK),
    ("git push origin master", "feat", ASK),
    ("git push origin release/1.2", "feat", ASK),
    ("git push origin HEAD:main", "feat", ASK),
    ("git push origin +main", "feat", ASK),
    ("git push --force origin main", "feat", ASK),
    ("git push origin feat:refs/heads/main", "feat", ASK),
    ("git push origin :main", "feat", ASK),
    ("git push --delete origin main", "feat", ASK),
    ("git push origin feat main", "feat", ASK),
    ("git -C /x push origin main", "feat", ASK),
    ("git push", "main", ASK),
    ("git push -u origin", "main", ASK),
    ("git push origin HEAD", "main", ASK),
    ("git push", "release/2.0", ASK),
    ("git push --all", "feat", ASK),
    # deny: the EnterWorktree default branch name
    ("git push -u origin worktree-probing-control", "main", DENY),
    ("git push", "worktree-probing-control", DENY),
    ("git push origin HEAD", "worktree-x", DENY),
    # allow: pushes to other branches
    ("git push origin kauki/feat/x", "main", ALLOW),
    ("git push -u origin kauki/feat/x", "main", ALLOW),
    ("git push origin HEAD:kauki/feat/x", "main", ALLOW),
    ("git push --force-with-lease origin kauki/feat/x", "main", ALLOW),
    ("git push", "feat", ALLOW),
    ("git push origin HEAD", "feat", ALLOW),
    ("git push origin mainline", "feat", ALLOW),
    ("git push origin feature-main", "feat", ALLOW),
    ("git push origin release-notes", "feat", ALLOW),
    ("git push", "", ALLOW),  # detached HEAD / not a repo: nothing to resolve
    # ask: tag pushes
    ("git push --tags", "feat", ASK),
    ("git push origin v1.0 --tags", "feat", ASK),
    ("git push --follow-tags", "feat", ASK),
    ("git push origin refs/tags/v1.0", "feat", ASK),
    ("git push origin HEAD:refs/tags/v1.0", "feat", ASK),
    ("git push origin tag v1.0", "feat", ASK),
    # ask: creating tags; allow: listing / deleting
    ("git tag v1.0", "feat", ASK),
    ("git tag -a v1.0 -m 'release'", "feat", ASK),
    ("git tag -s v1.0 HEAD~1", "feat", ASK),
    ("git tag", "feat", ALLOW),
    ("git tag -l", "feat", ALLOW),
    ("git tag --list 'v*'", "feat", ALLOW),
    ("git tag -d v1.0", "feat", ALLOW),
    # quoted strings must not trigger
    ('echo "git add -A"', "feat", ALLOW),
    ("echo 'git push origin main'", "main", ALLOW),
    ('git commit -m "git add . && gh pr merge 1"', "feat", ALLOW),
    ('git commit -m "$(cat <<\'EOF\'\ngit tag v1\nEOF\n)"', "feat", ALLOW),
    # heredoc bodies are text, not commands: notes and commit messages that mention a banned command
    ("cat > n.md <<'EOF'\ngit add .\nEOF", "feat", ALLOW),
    ("git commit -F - <<'EOF'\nmsg\ngit add -A is banned\nEOF", "feat", ALLOW),
    ("git commit -F - <<'EOF'\nnever git push origin main\nEOF", "feat", ALLOW),
    ("cat <<EOF > a.sh\ngh pr merge 12\nEOF", "feat", ALLOW),
    ("cat > n.md <<'EOF'\nnotes\nEOF\ngit add -A", "feat", DENY),  # a real command after the heredoc still is
    ("cat > n.md <<'EOF' && git add .\nnotes\nEOF", "feat", DENY),  # the rest of the heredoc line is a command
    # review findings: a heredoc fed to a shell, an unquoted heredoc that substitutes, a quoted << that is no heredoc
    ("bash <<'EOF'\ngit push origin main\ngit add -A\nEOF", "feat", DENY),
    ("bash <<'EOF'\ngit push origin main\nEOF", "feat", ASK),
    ("sh <<EOF\ngit add -A\nEOF", "feat", DENY),
    ("ssh host <<'EOF'\ngit add -A\nEOF", "feat", DENY),
    ("cat > a <<EOF\n$(git add -A)\nEOF", "feat", DENY),
    ("cat > a <<EOF\ngit add -A is banned\nEOF", "feat", ALLOW),
    ("echo '<<X'\ngit add -A\nX\n", "feat", DENY),
    ("git add .vscode/x .", "feat", DENY),  # the strictest decision wins, whatever the argument order
    ("git add -u .", "feat", ALLOW),  # update tracked files only: the very command the deny recommends
    # a branch name built from a shell variable: the first segment is the nick, the rest must still match
    ("git checkout -b $NICK/fix/hooks/heredoc", "main", ALLOW),
    ("git checkout -b ${nick}/feat/x/y", "main", ALLOW),
    ("git checkout -b $NICK/bad", "main", DENY),
    ("git checkout -b kauki/fix/$COMPONENT/y", "main", ALLOW),  # dynamic middle: cannot verify, fail open
    ('grep "gh pr merge" notes.md', "feat", ALLOW),
    ("rg 'git push --tags' .", "feat", ALLOW),
    ('echo "a && git add -A"', "feat", ALLOW),
    ('git log --grep="git add -A"', "feat", ALLOW),
    ('gh pr create --body "run gh pr merge later"', "feat", ALLOW),
    # compound commands
    ("git add src/a.rs && git commit -m x && git push origin kauki/x", "feat", ALLOW),
    ("git add src/a.rs && git push origin main", "feat", ASK),
    ("git add -A && git push origin main", "feat", DENY),
    ("git status\ngit tag v1", "feat", ASK),
    ("git fetch | cat; git tag v1", "feat", ASK),
    ("git fetch || git add .", "feat", DENY),
    ("sleep 1 & git push --tags", "feat", ASK),
    ("(cd /x && git push origin main)", "feat", ASK),
    # unrelated
    ("ls -la", "feat", ALLOW),
    ("", "feat", ALLOW),
    ("git status", "feat", ALLOW),
    ("git commit -m x", "feat", ALLOW),
    ("cargo add serde", "feat", ALLOW),
    ('echo "unterminated', "feat", ALLOW),  # unparseable: fail open
    # ask: stray agent-tool config
    ("git add opencode.json", "feat", ASK),
    ("git add .gemini/settings.json", "feat", ASK),
    ("git add .github/copilot-instructions.md", "feat", ASK),
    ("git add src/vscode_ext.rs", "feat", ALLOW),
    # ask: destructive git
    ("git push --force origin feat", "feat", ASK),
    ("git push -f origin feat", "feat", ASK),
    ("git reset --hard", "feat", ASK),
    ("git reset --hard HEAD~1", "feat", ASK),
    ("git clean -fd", "feat", ASK),
    # allow: safe forms of the above
    ("git push --force-with-lease origin feat", "feat", ALLOW),
    ("git reset --hard origin/main", "feat", ALLOW),
    ("git reset --soft HEAD~1", "feat", ALLOW),
    ("git clean -n", "feat", ALLOW),
    ("git clean -nfd", "feat", ALLOW),
    # deny: shell-substituted commit messages, bulk cargo update, comma-list close
    ('git commit -m "fix `x`"', "feat", DENY),
    ('git commit -m "fix $(date)"', "feat", DENY),
    ('git commit -m "fix x"', "feat", ALLOW),
    ("git commit -F msg.txt", "feat", ALLOW),
    ("git commit -m \"$(cat <<'EOF'\nfix `x`\nEOF\n)\"", "feat", ALLOW),
    ("cargo update", "feat", DENY),
    ("cargo update -p serde --precise 1.0.1", "feat", ALLOW),
    ("cargo update --precise 1.0.1 serde", "feat", ALLOW),
    ("cargo check", "feat", ALLOW),
    ('gh pr create --title t --body "Closes #1, #2"', "feat", DENY),
    ('gh pr create --title t --body "Closes #1\nCloses #2"', "feat", ALLOW),
    # deny: branch names off <nick>/<type>/<component>/<description>
    ("git checkout -b feat", "main", DENY),
    ("git checkout -b kauki/feat", "main", DENY),
    ("git checkout -B fix-the-thing", "main", DENY),
    ("git checkout -b kauki/feature/x/y", "main", DENY),
    ("git checkout -b Kauki/feat/x/y", "main", DENY),
    ("git switch -c my-branch", "main", DENY),
    ("git switch -C kauki/fix/x", "main", DENY),
    ("git branch my-branch", "main", DENY),
    ("git branch my-branch origin/main", "main", DENY),
    ("git worktree add ../wt -b my-branch", "main", DENY),
    ("git worktree add -b my-branch ../wt origin/main", "main", DENY),
    ("git -C /repo checkout -b my-branch", "main", DENY),
    ("git fetch && git checkout -b my-branch origin/main", "main", DENY),
    # allow: conforming names, other branch forms, exempt prefixes
    ("git checkout -b kauki/feat/session/1-hop-integration-test", "main", ALLOW),
    ("git checkout -b kauki/chore/nix/bump-deps origin/main", "main", ALLOW),
    ("git switch -c kauki/fix/hooks/branch-name-guard", "main", ALLOW),
    ("git branch kauki/docs/instructions/git-merge-exception origin/main", "main", ALLOW),
    ("git worktree add ../wt -b kauki/feat/a/b origin/main", "main", ALLOW),
    ("git checkout -b release/1.2", "main", ALLOW),
    ("git checkout -b renovate/nixpkgs", "main", ALLOW),
    ("git checkout -b dependabot/cargo/serde-1.0", "main", ALLOW),
    ("git checkout main", "feat", ALLOW),
    ("git checkout -- src/a.rs", "feat", ALLOW),
    ("git switch main", "feat", ALLOW),
    ("git branch", "feat", ALLOW),
    ("git branch -a", "feat", ALLOW),
    ("git branch --list 'kauki/*'", "feat", ALLOW),
    ("git branch --show-current", "feat", ALLOW),
    ("git branch -d my-branch", "feat", ALLOW),
    ("git branch -D my-branch", "feat", ALLOW),
    ("git branch -m old new", "feat", ALLOW),
    ("git branch -vv", "feat", ALLOW),
    ("git branch --set-upstream-to=origin/main", "feat", ALLOW),
    ("git worktree add ../wt", "feat", ALLOW),
    ("git worktree add ../wt kauki/feat/a/b", "feat", ALLOW),
    ("git worktree list", "feat", ALLOW),
    ("git worktree remove ../wt", "feat", ALLOW),
    ('echo "git checkout -b my-branch"', "feat", ALLOW),
]


class DecideTable(unittest.TestCase):
    def test_table(self):
        for command, branch, want in CASES:
            with self.subTest(command=command, branch=branch):
                decision, reason = guard.decide(command, "/cwd", lambda d, b=branch: b)
                self.assertEqual(decision, want, reason)
                if want != ALLOW:
                    self.assertTrue(reason)


ALLOWED = frozenset({"acme/widget"})

# (command, origin the fake repo resolver reports, expected decision) with ALLOWED as the allowlist
MERGE_ALLOWLIST_CASES = [
    # allowed repo, named explicitly
    ("gh pr merge 12 -R acme/widget", "", ALLOW),
    ("gh pr merge 12 --auto -R acme/widget", "", ALLOW),
    ("gh -R acme/widget pr merge 12", "", ALLOW),
    ("gh pr merge 12 --repo acme/widget", "", ALLOW),
    ("gh pr merge 12 --repo=acme/widget", "", ALLOW),
    ("gh pr merge 12 -R github.com/acme/widget", "", ALLOW),
    ("gh pr merge 12 -R Acme/Widget", "", ALLOW),
    ("gh api -X PUT repos/acme/widget/pulls/3/merge", "", ALLOW),
    # allowed repo, resolved from the cwd's origin
    ("gh pr merge 12 --auto", "acme/widget", ALLOW),
    ("cd /x && gh pr merge 1", "acme/widget", ALLOW),
    # other repos still ask
    ("gh pr merge 12 -R o/r", "acme/widget", ASK),
    ("gh pr merge 12", "o/r", ASK),
    ("gh pr merge 12", "", ASK),
    ("gh api -X PUT repos/o/r/pulls/3/merge", "acme/widget", ASK),
    ("gh pr merge 12 -R acme/widget-fork", "", ASK),
    # the allowlist covers merges only, never pushes or tags
    ("git push origin main", "acme/widget", ASK),
    ("git push --tags", "acme/widget", ASK),
    ("gh pr merge 1 -R acme/widget && git push origin main", "acme/widget", ASK),
    ("gh pr merge 1 -R acme/widget && git add -A", "", DENY),
]


class MergeAllowlist(unittest.TestCase):
    def test_table(self):
        for command, origin, want in MERGE_ALLOWLIST_CASES:
            with self.subTest(command=command, origin=origin):
                decision, reason = guard.decide(
                    command, "/cwd", lambda d: "feat", resolve_repo=lambda d, o=origin: o, merge_repos=ALLOWED
                )
                self.assertEqual(decision, want, reason)

    def test_empty_allowlist_keeps_asking(self):
        decision, _ = guard.decide(
            "gh pr merge 12 -R acme/widget", "/cwd", lambda d: "feat",
            resolve_repo=lambda d: "acme/widget", merge_repos=frozenset(),
        )
        self.assertEqual(decision, ASK)

    def test_repo_resolver_sees_the_cd_directory(self):
        seen = []
        guard.decide("cd /y && gh pr merge 1", "/cwd", lambda d: "feat",
                     resolve_repo=lambda d: seen.append(d) or "", merge_repos=ALLOWED)
        self.assertEqual(seen, ["/y"])

    def test_env_parsing(self):
        self.assertEqual(guard.parse_merge_repos(" acme/widget, O/R  x/y "),
                         frozenset({"acme/widget", "o/r", "x/y"}))
        self.assertEqual(guard.parse_merge_repos(""), frozenset())
        self.assertEqual(guard.parse_merge_repos(None), frozenset())

    def test_repo_from_remote_url(self):
        for url in ("git@github.com:acme/widget.git", "https://github.com/acme/widget",
                    "https://github.com/acme/widget.git", "ssh://git@github.com/acme/widget.git"):
            with self.subTest(url=url):
                self.assertEqual(guard.repo_slug(url), "acme/widget")


class ResolverTarget(unittest.TestCase):
    """The branch resolver must see the directory the push actually runs in."""

    def resolved_dirs(self, command):
        seen = []
        guard.decide(command, "/cwd", lambda d: seen.append(d) or "feat")
        return seen

    def test_cwd_default(self):
        self.assertEqual(self.resolved_dirs("git push"), ["/cwd"])

    def test_dash_c(self):
        self.assertEqual(self.resolved_dirs("git -C /x push"), ["/x"])

    def test_relative_dash_c(self):
        self.assertEqual(self.resolved_dirs("git -C sub push"), ["/cwd/sub"])

    def test_cd_prefix(self):
        self.assertEqual(self.resolved_dirs("cd /y && git push"), ["/y"])

    def test_not_called_when_refspec_explicit(self):
        self.assertEqual(self.resolved_dirs("git push origin kauki/x"), [])


class EndToEnd(unittest.TestCase):
    def run_hook(self, payload, raw=None):
        return subprocess.run(
            [sys.executable, HOOK],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, timeout=20,
        )

    def test_deny_schema(self):
        r = self.run_hook({"tool_name": "Bash", "cwd": "/", "tool_input": {"command": "git add -A"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("git add", out["permissionDecisionReason"])

    def test_ask_schema(self):
        r = self.run_hook({"tool_name": "Bash", "cwd": "/", "tool_input": {"command": "gh pr merge 3"}})
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "ask")

    def test_allow_is_silent(self):
        r = self.run_hook({"tool_name": "Bash", "cwd": "/", "tool_input": {"command": "git add src/a.rs"}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_other_tool_ignored(self):
        r = self.run_hook({"tool_name": "Read", "tool_input": {"command": "git add -A"}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_malformed_input_fails_open(self):
        for raw in ("", "not json", "[]", '{"tool_name":"Bash"}', '{"tool_name":"Bash","tool_input":{"command":null}}'):
            with self.subTest(raw=raw):
                r = self.run_hook(None, raw=raw)
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_bare_push_uses_real_branch(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
            r = self.run_hook({"tool_name": "Bash", "cwd": d, "tool_input": {"command": "git push"}})
            self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
            subprocess.run(["git", "-C", d, "checkout", "-q", "-b", "kauki/feat/x"], check=True)
            r = self.run_hook({"tool_name": "Bash", "cwd": d, "tool_input": {"command": "git push"}})
            self.assertEqual(r.stdout, "")

    def test_merge_allowlist_from_env_and_origin(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "remote", "add", "origin", "git@github.com:acme/widget.git"],
                           check=True)
            payload = {"tool_name": "Bash", "cwd": d, "tool_input": {"command": "gh pr merge 3 --auto"}}
            env = dict(os.environ, GIT_GUARD_MERGE_REPOS="acme/widget")
            r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True,
                               text=True, timeout=20, env=env)
            self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            env["GIT_GUARD_MERGE_REPOS"] = "other/repo"
            r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True,
                               text=True, timeout=20, env=env)
            self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_bare_push_outside_repo_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_hook({"tool_name": "Bash", "cwd": d, "tool_input": {"command": "git push"}})
            self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()


# (command, whether it needs git-workflow loaded first)
WORKFLOW_CASES = [
    ("git commit -m x", True),
    ("git push -u origin kauki/feat/a/b", True),
    ("git merge --ff-only x", True),
    ("git rebase origin/main", True),
    ("git cherry-pick abc", True),
    ("git reset --soft HEAD~1", True),
    ("git tag v1", True),
    ("git checkout -b kauki/feat/a/b", True),
    ("git switch -c kauki/feat/a/b", True),
    ("git branch kauki/feat/a/b", True),
    ("git worktree add ../wt -b kauki/feat/a/b", True),
    ("git worktree add ../wt", True),
    ("git -C /repo commit -m x", True),
    ("cd /repo && git push", True),
    ("FOO=1 git commit -m x", True),
    ('bash -c "git commit -m x"', True),
    ("gh pr create --draft", True),
    ("gh pr merge 3", True),
    ("gh pr ready 3", True),
    ("gh pr comment 3 -b x", True),
    ("gh issue create --title t", True),
    # read-only and non-workflow
    ("git status", False),
    ("git log --oneline", False),
    ("git diff", False),
    ("git show HEAD", False),
    ("git fetch origin", False),
    ("git branch", False),
    ("git branch --show-current", False),
    ("git branch -d x", False),
    ("git worktree list", False),
    ("git checkout main", False),
    ("git checkout -- src/a.rs", False),
    ("git switch main", False),
    ("git tag -l", False),
    ("git add src/a.rs", False),
    ("gh pr view 3", False),
    ("gh pr list", False),
    ("gh pr checks 3", False),
    ("gh issue view 3", False),
    ("gh api repos/o/r", False),
    ("ls -la", False),
    ("", False),
    ('echo "git commit -m x"', False),
    ('grep "git push" notes.md', False),
    ('echo "unterminated', False),
]


class NeedsWorkflow(unittest.TestCase):
    def test_table(self):
        for command, want in WORKFLOW_CASES:
            with self.subTest(command=command):
                self.assertEqual(guard.needs_workflow(command), want)


SKILL_CALL = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Skill", "input": {"skill": "git-workflow"}}]}}
NAMESPACED_CALL = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Skill", "input": {"skill": "my-plugin:git-workflow"}}]}}
PLUGIN_CALL = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Skill", "input": {"skill": "git:workflow"}}]}}
OTHER_SKILL = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Skill", "input": {"skill": "swe:rust"}}]}}
SLASH = {"type": "user", "message": {"role": "user", "content":
    "<command-message>git-workflow</command-message>\n<command-name>/git-workflow</command-name>"}}
SLASH_BLOCK = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text":
    "<command-message>my-plugin:git-workflow</command-message>\n<command-name>/my-plugin:git-workflow</command-name>"}]}}
MENTION = {"type": "user", "message": {"role": "user", "content":
    'remember {"skill": "git-workflow"} is a skill and git-workflow too'}}
MENTION_TAGS = {"type": "assistant", "message": {"content": [{"type": "text", "text":
    "a fixture: <command-message>git-workflow</command-message><command-name>/git-workflow</command-name>"}]}}


class WorkflowLoaded(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state")

    def transcript(self, *entries):
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return path

    def loaded(self, path, sid="s1"):
        data = {"session_id": sid}
        if path is not None:
            data["transcript_path"] = path
        return guard.workflow_loaded(data, self.state)

    def test_skill_call_counts(self):
        self.assertTrue(self.loaded(self.transcript(OTHER_SKILL, SKILL_CALL)))

    def test_namespaced_skill_call_counts(self):
        self.assertTrue(self.loaded(self.transcript(NAMESPACED_CALL)))
        self.assertTrue(self.loaded(self.transcript(PLUGIN_CALL)))

    def test_slash_command_counts(self):
        self.assertTrue(self.loaded(self.transcript(SLASH)))

    def test_slash_command_in_content_blocks_counts(self):
        self.assertTrue(self.loaded(self.transcript(SLASH_BLOCK)))

    def test_quoted_command_tags_do_not(self):
        self.assertFalse(self.loaded(self.transcript(MENTION_TAGS)))

    def test_other_skill_does_not(self):
        self.assertFalse(self.loaded(self.transcript(OTHER_SKILL)))

    def test_text_mention_does_not(self):
        self.assertFalse(self.loaded(self.transcript(MENTION)))

    def test_empty_transcript_does_not(self):
        self.assertFalse(self.loaded(self.transcript()))

    def test_base_directory_banner_does_not_count(self):
        path = os.path.join(self.tmp.name, "banner.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": "Base directory for this skill: /x/plugin-dirs/git/skills/workflow\n\n#"}]}}) + "\n")
        self.assertFalse(self.loaded(path))

    def test_no_transcript_path_fails_open(self):
        self.assertTrue(self.loaded(None))

    def test_missing_transcript_file_fails_open(self):
        self.assertTrue(self.loaded(os.path.join(self.tmp.name, "gone.jsonl")))

    def test_found_once_is_cached_per_session(self):
        path = self.transcript(SKILL_CALL)
        self.assertTrue(self.loaded(path, "a"))
        os.remove(path)
        self.assertTrue(self.loaded(path, "a"))  # marker, not the transcript
        self.assertTrue(self.loaded(path, "b"))  # other session: missing file fails open
        path = self.transcript(OTHER_SKILL)
        self.assertFalse(self.loaded(path, "c"))


class WorkflowGateEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_hook(self, tool, tool_input, *entries):
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        payload = {"tool_name": tool, "cwd": "/", "session_id": "sid", "transcript_path": path,
                   "tool_input": tool_input}
        env = dict(os.environ, GIT_GUARD_STATE_DIR=os.path.join(self.tmp.name, "state"))
        return subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=20, env=env)

    def test_git_commit_denied_until_skill_loaded(self):
        r = self.run_hook("Bash", {"command": "git commit -m x"}, OTHER_SKILL)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("git:workflow", out["permissionDecisionReason"])
        self.assertIn("Skill", out["permissionDecisionReason"])

    def test_git_commit_allowed_once_loaded(self):
        r = self.run_hook("Bash", {"command": "git commit -m x"}, SKILL_CALL)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_read_only_git_never_gated(self):
        r = self.run_hook("Bash", {"command": "git status"}, OTHER_SKILL)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_enter_worktree_denied_until_skill_loaded(self):
        r = self.run_hook("EnterWorktree", {"name": "x"}, OTHER_SKILL)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")

    def test_enter_worktree_allowed_once_loaded(self):
        r = self.run_hook("EnterWorktree", {"name": "x"}, SKILL_CALL)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_guard_rule_still_applies_once_loaded(self):
        r = self.run_hook("Bash", {"command": "git add -A"}, SKILL_CALL)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


class ForgedLoad(unittest.TestCase):
    """Text a tool or the agent produced never unlocks the workflow gate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def commit_decision(self, *entries):
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        payload = {"tool_name": "Bash", "cwd": "/", "session_id": "sid", "transcript_path": path,
                   "tool_input": {"command": "git commit -m x"}}
        env = dict(os.environ, GIT_GUARD_STATE_DIR=os.path.join(self.tmp.name, "state"))
        r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True,
                           text=True, timeout=20, env=env)
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout else "allow"

    def test_banner_or_tag_in_a_tool_result_does_not_unlock(self):
        for text in ("Base directory for this skill: /x/plugin-dirs/git/skills/workflow",
                     "<command-message>git:workflow</command-message>"):
            entry = {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t", "content": text}]}}
            self.assertEqual(self.commit_decision(entry), "deny", text)

    def test_a_user_text_block_holding_the_banner_does_not_unlock(self):
        for path in ("/x/plugin-dirs/git/skills/workflow", "/x/plugin-dirs/other/skills/workflow"):
            entry = {"type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": f"Base directory for this skill: {path}\n\n# body"}]}}
            self.assertEqual(self.commit_decision(entry), "deny", path)


class SkillLoadedModuleMissing(unittest.TestCase):
    """If the sibling skill_loaded.py is gone, only the skill gate fails open: every other rule still applies."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        shutil.copy(HOOK, os.path.join(self.tmp.name, "git-guard"))  # no skill_loaded.py beside it

    def run_hook(self, command):
        payload = {"tool_name": "Bash", "cwd": "/", "session_id": "s", "tool_input": {"command": command}}
        return subprocess.run([sys.executable, os.path.join(self.tmp.name, "git-guard")], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=20)

    def test_other_rules_still_deny(self):
        r = self.run_hook("git add -A")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("deny", r.stdout)
        self.assertNotIn("git:workflow skill first", r.stdout)

    def test_skill_gate_fails_open_with_one_note(self):
        r = self.run_hook("git commit -m x")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(r.stderr.count("skill_loaded"), 1, r.stderr)


class SubagentWorkflowLoaded(unittest.TestCase):
    """A subagent payload carries the PARENT's transcript_path plus agent_id. The subagent's own load lives in
    <session>/subagents/agent-<agent_id>.jsonl; each agent must have loaded the skill itself."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(os.path.join(self.tmp.name, "proj", "sid", "subagents"))

    def write(self, rel, *entries):
        path = os.path.join(self.tmp.name, "proj", rel)
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return path

    def loaded(self, agent_id="a1", sid="sid"):
        parent = os.path.join(self.tmp.name, "proj", "sid.jsonl")
        return guard.workflow_loaded(
            {"session_id": sid, "transcript_path": parent, "agent_id": agent_id}, self.state)

    def test_subagent_own_load_counts(self):
        self.write("sid.jsonl", OTHER_SKILL)
        self.write("sid/subagents/agent-a1.jsonl", SKILL_CALL)
        self.assertTrue(self.loaded())

    def test_parent_load_does_not_cover_subagent(self):
        self.write("sid.jsonl", SKILL_CALL)
        self.write("sid/subagents/agent-a1.jsonl", OTHER_SKILL)
        self.assertFalse(self.loaded())

    def test_parent_marker_does_not_cover_subagent(self):
        self.write("sid.jsonl", SKILL_CALL)
        self.write("sid/subagents/agent-a1.jsonl", OTHER_SKILL)
        self.assertTrue(guard.workflow_loaded(
            {"session_id": "sid", "transcript_path": os.path.join(self.tmp.name, "proj", "sid.jsonl")},
            self.state))  # parent call writes the session marker
        self.assertFalse(self.loaded())

    def test_marker_is_per_agent(self):
        self.write("sid.jsonl", OTHER_SKILL)
        self.write("sid/subagents/agent-a1.jsonl", SKILL_CALL)
        self.write("sid/subagents/agent-a2.jsonl", OTHER_SKILL)
        self.assertTrue(self.loaded("a1"))
        self.assertFalse(self.loaded("a2"))

    def test_missing_subagent_transcript_fails_open(self):
        self.write("sid.jsonl", OTHER_SKILL)
        self.assertTrue(self.loaded("ghost"))

    def test_end_to_end_denied_when_only_parent_loaded(self):
        parent = self.write("sid.jsonl", SKILL_CALL)
        self.write("sid/subagents/agent-a1.jsonl", OTHER_SKILL)
        payload = {"tool_name": "Bash", "cwd": "/", "session_id": "sid", "transcript_path": parent,
                   "agent_id": "a1", "tool_input": {"command": "git commit -m x"}}
        env = dict(os.environ, GIT_GUARD_STATE_DIR=self.state)
        r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=20, env=env)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")


class ThrowawayRepoAndMessages(unittest.TestCase):
    """git add . is allowed in a scratch repo (a temp dir with no remote), never in a real checkout; the
    deny messages name the safe command and the caller's nick."""

    def make_repo(self, parent, remote=False):
        subprocess.run(["git", "init", "-q", parent], check=True)
        if remote:
            subprocess.run(["git", "-C", parent, "remote", "add", "origin", "git@github.com:o/r.git"], check=True)

    def test_add_dot_allowed_in_scratch_repo_without_remote(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.make_repo(tmp)
            decision, _ = guard.decide("git add .", tmp, lambda d: "main")
            self.assertEqual(decision, ALLOW)

    def test_add_dot_still_denied_in_temp_repo_with_a_remote(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.make_repo(tmp, remote=True)  # a /tmp worktree of a real project
            decision, _ = guard.decide("git add .", tmp, lambda d: "main")
            self.assertEqual(decision, DENY)

    def test_add_dot_still_denied_outside_the_temp_dir(self):
        here = os.path.dirname(os.path.abspath(__file__))
        decision, _ = guard.decide("git add .", here, lambda d: "main")
        self.assertEqual(decision, DENY)

    def test_add_all_reason_names_the_safe_commands(self):
        _, reason = guard.decide("git add -A", "/cwd", lambda d: "main")
        self.assertIn("git add -u", reason)
        self.assertIn("git status --porcelain", reason)

    def test_bad_branch_reason_shows_the_nick_and_an_example(self):
        old = os.environ.get("GIT_CONFIG_CUSTOMAGENTS_NICK")
        os.environ["GIT_CONFIG_CUSTOMAGENTS_NICK"] = "ada"
        try:
            _, reason = guard.decide("git checkout -b my-branch", "/definitely/not/a/repo", lambda d: "main")
        finally:
            if old is None:
                os.environ.pop("GIT_CONFIG_CUSTOMAGENTS_NICK")
            else:
                os.environ["GIT_CONFIG_CUSTOMAGENTS_NICK"] = old
        self.assertIn("ada/feat/", reason)  # a ready-to-use example with the resolved nick


    def test_scratch_exemption_does_not_follow_a_cd_out_of_a_subshell(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.make_repo(tmp)
            here = os.path.dirname(os.path.abspath(__file__))
            for cmd in (f"(cd {tmp} && make); git add -A", f"true || cd {tmp}; git add -A", f"cd {tmp} && git add -A"):
                with self.subTest(cmd=cmd):
                    self.assertEqual(guard.decide(cmd, here, lambda d: "main")[0], DENY)

    def test_scratch_exemption_not_applied_when_git_dir_points_elsewhere(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.make_repo(tmp)
            for cmd in ("git --git-dir=/real/.git --work-tree=/real add -A", "GIT_DIR=/real/.git git add -A"):
                with self.subTest(cmd=cmd):
                    self.assertEqual(guard.decide(cmd, tmp, lambda d: "main")[0], DENY)

    def test_scratch_repo_under_slash_tmp_is_exempt(self):
        import shutil
        d = tempfile.mkdtemp(dir="/tmp")
        try:
            self.make_repo(d)
            self.assertEqual(guard.decide("git add .", d, lambda x: "main")[0], ALLOW)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_heredoc_strip_is_linear_on_hostile_input(self):
        import time
        for cmd in ("cat <<EOF\n" + " \n" * 100000, "cat <<EOF\n" * 20000, "x" * 300000):
            t = time.time()
            guard.decide(cmd, "/cwd", lambda d: "main")
            # Catches a quadratic strip; the 2s bound flaked on a loaded CI runner (2.19s).
            self.assertLess(time.time() - t, 10.0)

    def test_unset_nick_is_said_plainly(self):
        old = os.environ.pop("GIT_CONFIG_CUSTOMAGENTS_NICK", None)
        try:
            _, reason = guard.decide("git checkout -b my-branch", "/definitely/not/a/repo", lambda d: "main")
        finally:
            if old is not None:
                os.environ["GIT_CONFIG_CUSTOMAGENTS_NICK"] = old
        self.assertIn("no nick is configured", reason)
