"""Review-driven cases for git-guard: line continuations, wrappers, commit message forms, heredoc consumers,
gh merge targets, read-only listings. Run: python3 -m pytest engineering/tools/git/hooks/tests"""
import importlib.machinery
import importlib.util
import os
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "git-guard")
_loader = importlib.machinery.SourceFileLoader("git_guard_review", HOOK)
_spec = importlib.util.spec_from_loader("git_guard_review", _loader)
guard = importlib.util.module_from_spec(_spec)
_loader.exec_module(guard)

DENY, ASK, ALLOW = "deny", "ask", "allow"
ALLOWED = frozenset({"acme/widget"})


def decide(command, repo="", merge_repos=frozenset()):
    return guard.decide(command, "/cwd", lambda d: "feat", lambda d: repo, merge_repos)[0]


def table(test, cases, **kw):
    for command, want in cases:
        with test.subTest(command=command):
            test.assertEqual(decide(command, **kw), want)


class LineContinuation(unittest.TestCase):
    def test_backslash_newline_joins_before_tokenising(self):
        table(self, [
            ("git add \\\n-A", DENY),
            ("git add \\\n  .", DENY),
            ("git push \\\n--force origin feat", ASK),
            ("git push \\\norigin main", ASK),
            ("git \\\npush origin main", ASK),
            ("git add \\\nsrc/a.rs", ALLOW),
        ])

    def test_needs_workflow_sees_the_joined_command(self):
        self.assertTrue(guard.needs_workflow("git \\\ncommit -m x"))


class Wrappers(unittest.TestCase):
    def test_table(self):
        table(self, [
            ("timeout 60 git push origin main", ASK),
            ("timeout -k 5 60 git push origin main", ASK),
            ("timeout --signal=KILL 10 git add -A", DENY),
            ("timeout --kill-after 5 10 git add -A", DENY),
            ("sudo git push origin main", ASK),
            ("sudo -u bob git push origin main", ASK),
            ("sudo -E -H git add -A", DENY),
            ("sudo -- git add -A", DENY),
            ("nice -n 5 git push origin main", ASK),
            ("nice git add -A", DENY),
            ("ionice -c 3 git add -A", DENY),
            ("xargs git add -A", DENY),
            ("xargs -n 1 git add -A", DENY),
            ("stdbuf -oL git add -A", DENY),
            ("stdbuf -o L git add -A", DENY),
            ("setsid git add -A", DENY),
            ("env -u FOO git add -A", DENY),
            ("env -i git add -A", DENY),
            ("env -u A -u B X=1 git push origin main", ASK),
            ("env --unset FOO git add -A", DENY),
            ("env --unset=FOO git add -A", DENY),
            ("env -S 'git add -A'", DENY),
            ("command -p git add -A", DENY),
            ("builtin command git add -A", DENY),
            ("time -p git add -A", DENY),
            ("nohup git add -A", DENY),
            ("sudo timeout 5 nice -n 1 git add -A", DENY),
            # nothing risky behind the wrapper
            ("timeout 60 git status", ALLOW),
            ("sudo -u bob ls", ALLOW),
            ("env -u FOO ls", ALLOW),
            ("timeout 60", ALLOW),
            ("sudo", ALLOW),
            ("xargs", ALLOW),
        ])

    def test_needs_workflow_looks_through_wrappers(self):
        for command in ("timeout 60 git commit -m x", "sudo -u bob git push origin feat", "env -u A git commit -m x"):
            with self.subTest(command=command):
                self.assertTrue(guard.needs_workflow(command))


class CommitMessageForms(unittest.TestCase):
    def test_substitution_in_any_message_form_is_denied(self):
        table(self, [(c, DENY) for c in (
            'git commit -am "x `id`"',
            'git commit -m"x `id`"',
            'git commit -am"x $(id)"',
            'git commit -qm "$(id)"',
            'git commit --message="x `id`"',
            'git commit --message "x `id`"',
            'git commit -S -m "`id`"',
            'git commit -sm"`id`"',
            'git commit -a --amend -m "$(date)"',
            'git commit -vam "$(id)"',
        )])

    def test_plain_messages_and_file_forms_pass(self):
        table(self, [(c, ALLOW) for c in (
            'git commit -am "plain"',
            'git commit -m"plain"',
            "git commit -F msg.txt",
            "git commit -F -",
            "git commit --file=msg.txt",
            "git commit -a -m x",
            "git commit -C HEAD",
            "git commit --amend --no-edit",
        )])

    def test_quoted_heredoc_idiom_is_still_allowed(self):
        cmd = "git commit -m \"$(cat <<'EOF'\nbody\nEOF\n)\""
        self.assertEqual(decide(cmd), ALLOW)


class HeredocConsumers(unittest.TestCase):
    def test_body_piped_or_fed_to_a_shell_is_scanned(self):
        table(self, [(c, DENY) for c in (
            "cat <<'EOF' | bash\ngit add -A\nEOF",
            "cat <<EOF | sh\ngit add -A\nEOF",
            "cat <<'EOF' | sudo bash\ngit add -A\nEOF",
            "cat <<'EOF' | /bin/bash -s\ngit add -A\nEOF",
            "bash <<EOF\ngit add -A\nEOF",
            "sh -s <<EOF\ngit add -A\nEOF",
            "cat <<'EOF' | ssh host\ngit add -A\nEOF",
        )])

    def test_body_that_is_only_text_is_not_scanned(self):
        table(self, [(c, ALLOW) for c in (
            "cat <<'EOF' > notes.md\ngit add -A\nEOF",
            "cat <<'EOF' | grep sh\ngit add -A\nEOF",
            "cat <<'EOF' | wc -l\ngit add -A\nEOF",
            "git commit -F - <<'EOF'\nnever git add -A\nEOF",
        )])


class MergeTarget(unittest.TestCase):
    def test_target_comes_from_url_flag_or_gh_repo_not_the_cwd(self):
        table(self, [
            ("gh pr merge https://github.com/other/repo/pull/5", ASK),
            ("gh pr merge https://github.example.com/other/repo/pull/5/files", ASK),
            ("gh pr merge https://github.com/acme/widget/pull/5", ALLOW),
            ("GH_REPO=other/repo gh pr merge 5", ASK),
            ("GH_REPO=acme/widget gh pr merge 5", ALLOW),
            ("env GH_REPO=other/repo gh pr merge 5", ASK),
            ("gh pr merge -R other/repo 5", ASK),
            ("gh pr merge 5 --repo other/repo", ASK),
            ("gh pr merge 5", ALLOW),  # the cwd origin is the allowlisted repo
        ], repo="acme/widget", merge_repos=ALLOWED)

    def test_url_beats_an_allowlisted_cwd_only_when_it_names_another_repo(self):
        self.assertEqual(decide("gh pr merge https://github.com/acme/widget/pull/5", repo="other/repo",
                                merge_repos=ALLOWED), ALLOW)


class ReadOnlyListings(unittest.TestCase):
    TAG_LISTINGS = ("git tag --contains abc", "git tag --points-at HEAD", "git tag --merged main",
                    "git tag --no-merged main", "git tag --sort=-creatordate", "git tag --sort -creatordate",
                    "git tag -l 'v*'", "git tag --list", "git tag -n", "git tag -n5", "git tag --format='%(refname)'",
                    "git tag --format %(refname)")
    BRANCH_LISTINGS = ("git branch --points-at HEAD", "git branch --sort=-committerdate",
                       "git branch --sort committerdate", "git branch --contains abc", "git branch --merged",
                       "git branch --no-merged main", "git branch --format '%(refname)'", "git branch -l",
                       "git branch -a", "git branch -r", "git branch -v", "git branch -vv",
                       "git branch --no-contains abc", "git branch --show-current")

    def test_listings_are_allowed_and_need_no_workflow(self):
        for command in self.TAG_LISTINGS + self.BRANCH_LISTINGS:
            with self.subTest(command=command):
                self.assertEqual(decide(command), ALLOW)
                self.assertFalse(guard.needs_workflow(command))

    def test_creation_is_still_caught(self):
        self.assertEqual(decide("git tag v1"), ASK)
        self.assertTrue(guard.needs_workflow("git tag v1"))
        self.assertTrue(guard.needs_workflow("git branch kauki/feat/a/b"))
        self.assertEqual(decide("git branch badname"), DENY)


if __name__ == "__main__":
    unittest.main()
