"""Acceptance tests for the OWS 1.1.0 schema gate.

Run with: uv run --with pytest --with jsonschema --with pyyaml python -m pytest <this file> -q
"""
import hashlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "check_flow_schema.py"
SCHEMA = HERE.parent / "schemas" / "ows" / "workflow.yaml"
# sha256 of schema/workflow.yaml at tag v1.1.0 of serverlessworkflow/specification
PUBLISHED_SHA256 = "a2d181c56b1328b1f94fdf7086d15980f640352405b0811389704242a321f1c9"

VALID = """\
document:
  dsl: 1.1.0
  namespace: test
  name: demo
  version: 0.1.0
do:
  - first:
      set:
        x: 1
  - wait_for_it:
      listen:
        to:
          one:
            with:
              type: com.example.done
"""


def run(path, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra, str(path)],
        capture_output=True, text=True,
    )


def write(tmp_path, text):
    p = tmp_path / "flow.yaml"
    p.write_text(text)
    return p


def test_a_valid_fixture_passes(tmp_path):
    r = run(write(tmp_path, VALID))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_a_misspelled_task_key_fails(tmp_path):
    r = run(write(tmp_path, VALID.replace("set:", "sett:")))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OK" not in r.stdout


def test_an_unknown_key_inside_listen_fails(tmp_path):
    bad = VALID.replace("      listen:\n", "      listen:\n        bogus: true\n")
    r = run(write(tmp_path, bad))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "bogus" in r.stdout


def test_a_missing_file_is_an_error_not_a_pass(tmp_path):
    r = run(tmp_path / "nope.yaml")
    assert r.returncode == 2
    assert "OK" not in r.stdout


def test_without_jsonschema_exit_3_with_install_hint(tmp_path):
    p = write(tmp_path, VALID)
    # Block the import so the test is independent of what is installed.
    code = (
        "import sys, runpy; sys.modules['jsonschema'] = None; "
        f"sys.argv = [{str(SCRIPT)!r}, {str(p)!r}]; "
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "uv run --with jsonschema" in r.stderr
    assert "OK" not in r.stdout


def test_without_pyyaml_exit_3_with_install_hint(tmp_path):
    p = write(tmp_path, VALID)
    code = (
        "import sys, runpy; sys.modules['yaml'] = None; "
        f"sys.argv = [{str(SCRIPT)!r}, {str(p)!r}]; "
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "--with pyyaml" in r.stderr


def test_vendored_schema_matches_published_sha256():
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == PUBLISHED_SHA256


def test_vendored_license_notice_present():
    notice = SCHEMA.parent / "NOTICE"
    assert "Apache License" in notice.read_text()
