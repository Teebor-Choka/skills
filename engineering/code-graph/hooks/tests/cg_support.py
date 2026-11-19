"""Shared fixtures for the code-graph hook tests: a throwaway git repo, a fake codebase-memory-mcp that
logs its arguments, and a PATH built from symlinks so the real binary is never visible by accident."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

TOOLS = ["bash", "sh", "env", "jq", "git", "sed", "tr", "dirname", "basename", "cat", "head", "mkdir", "rmdir",
         "date", "printf", "id", "cksum", "cut", "rm", "sleep", "kill", "ps", "stat", "touch", "find", "sha1sum", "shasum", "sha256sum", "awk"]
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}


def make_repo(path):
    os.makedirs(path)
    git("init", "-q", "-b", "main", cwd=path)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=path)
    return path


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **GIT_ENV})


class Sandbox:
    """tmp/home, tmp/repo (git, one commit), tmp/bin (tool symlinks, optional fake graph binary)."""

    def __init__(self, with_binary=True, slow=0):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        self.repo = os.path.join(self.tmp, "repo")
        self.bin = os.path.join(self.tmp, "bin")
        self.calls = os.path.join(self.tmp, "calls.log")
        for d in (self.home, self.repo, self.bin):
            os.makedirs(d)
        git("init", "-q", "-b", "main", cwd=self.repo)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.repo)
        self.slow = slow
        for tool in TOOLS:
            found = shutil.which(tool)
            if found:
                os.symlink(found, os.path.join(self.bin, tool))
        if with_binary:
            fake = os.path.join(self.bin, "codebase-memory-mcp")
            with open(fake, "w") as f:
                f.write('#!/bin/sh\nprintf "%s\\n" "$*" >> "' + self.calls + '"\n' + (f"sleep {slow}\n" if slow else ""))
            os.chmod(fake, 0o755)

    @property
    def project(self):
        return self.repo.lstrip("/").replace("/", "-")

    def env(self, **extra):
        return {"PATH": self.bin, "HOME": self.home, "TMPDIR": self.tmp, **extra}

    def run(self, hook, payload, **extra_env):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        with open(hook) as f:
            cmd = [sys.executable, hook] if "python" in f.readline() else [hook]
        return subprocess.run(cmd, input=raw, capture_output=True, text=True, timeout=30,
                              env=self.env(**extra_env))

    def locks(self):
        cache = os.path.join(self.home, ".cache")
        return sorted(os.path.join(cache, n) for n in os.listdir(cache) if n.startswith("git-reindex.")) \
            if os.path.isdir(cache) else []

    def calls_seen(self, wait=0.0, n=1):
        """Lines the fake binary logged; waits up to `wait` seconds for `n` backgrounded calls."""
        deadline = time.time() + wait
        while True:
            try:
                with open(self.calls) as f:
                    lines = f.read().splitlines()
            except OSError:
                lines = []
            if len(lines) >= n or time.time() >= deadline:
                return lines
            time.sleep(0.05)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
