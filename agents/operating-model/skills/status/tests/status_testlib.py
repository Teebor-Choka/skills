"""Shared helpers for the status skill tests: paths, module loading and a generated fixture site."""

import importlib
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SKILL = TESTS.parent
SCRIPTS = SKILL / "scripts"
ASSETS = SKILL / "assets"
FIXTURE = TESTS / "fixture"
ORG_ROOT = SKILL.parent / "workflow"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name):
    """Import one of the skill's scripts by module name."""
    return importlib.import_module(name)


def fixture_argv(data_dir, work_package=True, ledger=True, ingest_log=None):
    """gen.py and serve.py arguments for a deterministic site: no gh, the fixture ledger and work package."""
    argv = ["--org-root", str(ORG_ROOT), "--data-dir", str(data_dir), "--no-gh"]
    if ledger:
        argv += ["--ledger", str(FIXTURE / "run.ledger")]
    if work_package:
        argv += ["--work-package", str(FIXTURE / "work-package")]
    if ingest_log:
        argv += ["--ingest", str(ingest_log)]
    return argv
