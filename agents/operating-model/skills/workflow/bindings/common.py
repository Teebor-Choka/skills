"""Shared pieces: the `gh` wrapper, secret redaction and the contract-checking adapter base.

`runner(argv, stdin, env) -> (returncode, stdout, stderr)` is the only door to the outside. Tests
inject a fake; the default runs the real `gh`. The token goes to the runner in `env` only, never in
argv or the request body, and every message that leaves this module is redacted.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL / "scripts"))

from op_conformance import PortError, check_schema  # noqa: E402

TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
TOKEN_SHAPES = re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class GhError(Exception):
    """`kind` is 'not-found' or 'unavailable'. The message is already redacted."""

    def __init__(self, kind, message=""):
        super().__init__(message)
        self.kind = kind


def redact(text, secrets=()):
    for s in secrets:
        if s:
            text = text.replace(s, "[REDACTED]")
    text = re.sub(r"(?i)(authorization:\s*)\S+(\s+\S+)?", r"\1[REDACTED]", text)
    return TOKEN_SHAPES.sub("[REDACTED]", text)


def default_runner(argv, stdin, env, timeout=60):
    done = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **env}, check=False)
    return done.returncode, done.stdout, done.stderr


class Gh:
    """`gh api` over one repository. `log` keeps argv and exit code per call: no env, body or output."""

    def __init__(self, repo, runner=None, env=None):
        parts = repo.split("/")
        if not REPO.fullmatch(repo) or any(set(p) == {"."} for p in parts):
            raise ValueError(f"repository must be owner/name: {repo!r}")
        self.repo, self.log = repo, []
        self._runner = runner or default_runner
        source = os.environ if env is None else env
        self._env = {k: source[k] for k in TOKEN_VARS if source.get(k)}
        if env is not None:
            self._env.update({k: v for k, v in env.items() if isinstance(v, str)})
        self._secrets = [v for k, v in self._env.items() if k in TOKEN_VARS]

    def _clean(self, text):
        return redact(text or "", self._secrets)

    def api(self, method, path, body=None, paginate=False):
        argv = ["gh", "api"]
        if method != "GET":
            argv += ["-X", method]
        if paginate:
            argv += ["--paginate", "--slurp"]
        argv.append(path)
        stdin = None
        if body is not None:
            argv += ["--input", "-"]
            stdin = json.dumps(body)
        try:
            rc, out, err = self._runner(argv, stdin, dict(self._env))
        except (OSError, TimeoutError, subprocess.TimeoutExpired) as e:
            self.log.append({"argv": argv, "rc": None})
            raise GhError("unavailable", f"gh did not run: {type(e).__name__}") from None
        self.log.append({"argv": argv, "rc": rc})
        if rc != 0:
            kind = "not-found" if ("404" in err or "Not Found" in err) else "unavailable"
            raise GhError(kind, f"gh api {method} {path}: {self._clean(err).strip()[:300]}")
        try:
            data = json.loads(out) if out.strip() else None
        except ValueError:
            raise GhError("unavailable", "gh returned output that is not JSON") from None
        if paginate:
            return [item for page in data for item in page]
        return data


class Adapter:
    """Validates input against the port contract, dispatches to `_op_<name>`, maps GhError to PortError."""

    port = ""
    unavailable = ""

    def __init__(self):
        self._contract = json.loads((_SKILL / "contracts" / f"{self.port.lower()}.json").read_text())

    def call(self, op, inp):
        spec = self._contract["operations"].get(op)
        if spec is None:
            raise PortError("invalid-input", f"unknown operation {op}")
        bad = check_schema(inp, spec["input"])
        if bad:
            raise PortError("invalid-input", bad[0])
        try:
            return getattr(self, "_op_" + op.replace("-", "_"))(inp)
        except GhError as e:
            code = "not-found" if e.kind == "not-found" and "not-found" in spec["errors"] else self.unavailable
            raise PortError(code, str(e)) from None
