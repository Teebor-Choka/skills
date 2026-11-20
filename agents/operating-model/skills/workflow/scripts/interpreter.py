"""Interpreter for the accepted OWS subset (stub for the red commit)."""

from dataclasses import dataclass, field


@dataclass
class StepRequest:
    key: str = ""
    rel: str = ""
    path: str = ""
    command: str = ""
    arguments: list = field(default_factory=list)
    argv: list = field(default_factory=list)
    role: str = ""
    brief: str = ""
    by: str = ""
    input: object = None
    limit: object = None
    run_id: str = ""
    accepted: dict = field(default_factory=dict)
    shell: dict = field(default_factory=dict)


@dataclass
class StepOutcome:
    exit_code: int = 0
    output: object = None
    stdout: object = None
    duration: float = 0.0
    error: object = None
    timed_out: bool = False


@dataclass
class JudgeRequest:
    key: str = ""
    item: int = 0
    role: str = ""
    rubric: str = ""
    run_id: str = ""
    invocation: str = ""


@dataclass
class RunResult:
    status: str = "error"
    errors: list = field(default_factory=list)
    error_objects: list = field(default_factory=list)
    events: list = field(default_factory=list)
    accepted: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    run_id: str = ""
    output: object = None
    context: object = None
    now: float = 0.0


class ScriptedHost:
    def __init__(self, steps=None, checks=None, judges=None, events=None, signed=None, outside=()):
        self.calls = []


class ProcessHost:
    def __init__(self, root, agent_run=None, events=(), verify=None):
        self.root = root


class Interpreter:
    def __init__(self, workflows, host, catalog=None, manifest=None):
        self.workflows = workflows
        self.host = host

    def run(self, name, input=None, run_id=None):
        return RunResult()
