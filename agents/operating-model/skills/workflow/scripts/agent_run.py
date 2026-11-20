"""Stub for the red run: every entry point fails at the assertion level, not at import."""
import sys


class _Todo:
    def __init__(self, *a, **k):
        pass

    def call(self, op, inp):
        return {}

    def history(self, run):
        return None

    def calls(self, run):
        return None


class ScriptedAdapter(_Todo):
    pass


class ClaudeCodeAdapter(_Todo):
    pass


class SessionStore(_Todo):
    pass


def validate_harness_contract(doc):
    return ["not implemented"]


def run_harness_conformance(contract, adapter, platform=None):
    return ["not implemented"]


def build_prompt(brief, context, task):
    return ""


def run_agent(*a, **k):
    return {}


def main(argv, env=None, stdout=None, stderr=None):
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
