"""Acceptance tests for the OWS 1.1.0 schema gate.

Run with: uv run --with pytest --with jsonschema --with pyyaml python -m pytest <this file> -q
"""
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "check_flow_schema.py"
SCHEMA = HERE.parent / "schemas" / "ows" / "workflow.yaml.upstream"
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


needs_deps = pytest.mark.skipif(
    importlib.util.find_spec("jsonschema") is None or importlib.util.find_spec("yaml") is None,
    reason="optional: uv run --with jsonschema --with pyyaml",
)


def run(path, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra, str(path)],
        capture_output=True, text=True,
    )


def write(tmp_path, text):
    p = tmp_path / "flow.yaml"
    p.write_text(text)
    return p


@needs_deps
def test_a_valid_fixture_passes(tmp_path):
    r = run(write(tmp_path, VALID))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


@needs_deps
def test_a_misspelled_task_key_fails(tmp_path):
    r = run(write(tmp_path, VALID.replace("set:", "sett:")))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OK" not in r.stdout


@needs_deps
def test_an_unknown_key_inside_listen_fails(tmp_path):
    bad = VALID.replace("      listen:\n", "      listen:\n        bogus: true\n")
    r = run(write(tmp_path, bad))
    assert r.returncode == 1, r.stdout + r.stderr
    # The schema reports an unknown key inside a task as the task failing every
    # alternative, so best_match points at the task and names the task kind as
    # unexpected. The valid fixture differs only by the bogus line.
    assert "/do/1/wait_for_it :: Unevaluated properties are not allowed ('listen' was unexpected)" in r.stdout
    assert "is not valid under any of the given schemas" not in r.stdout


@needs_deps
def test_a_missing_file_is_an_error_not_a_pass(tmp_path):
    r = run(tmp_path / "nope.yaml")
    assert r.returncode == 2
    assert "OK" not in r.stdout


def test_without_jsonschema_exit_3_with_install_hint(tmp_path):
    p = write(tmp_path, VALID)
    # Block one import and stub the other, so the test is independent of what is installed.
    r = run_code("import types; sys.modules['yaml'] = types.ModuleType('yaml'); sys.modules['jsonschema'] = None", p)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "uv run --with jsonschema" in r.stderr
    assert "'jsonschema'" in r.stderr
    assert "PyYAML" not in r.stderr.split("Run:")[0]
    assert "OK" not in r.stdout


def test_without_pyyaml_exit_3_with_install_hint(tmp_path):
    p = write(tmp_path, VALID)
    r = run_code("import types; sys.modules['jsonschema'] = types.ModuleType('jsonschema'); sys.modules['yaml'] = None", p)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "--with pyyaml" in r.stderr
    assert "'PyYAML'" in r.stderr
    assert "'jsonschema'" not in r.stderr
    assert "OK" not in r.stdout


def test_vendored_schema_matches_published_sha256():
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == PUBLISHED_SHA256


def test_vendored_license_notice_present():
    text = (SCHEMA.parent / "NOTICE").read_text()
    assert "Apache License, Version 2.0" in text
    assert "https://www.apache.org/licenses/LICENSE-2.0" in text
    assert "github.com/serverlessworkflow/specification/blob/v1.1.0/schema/workflow.yaml" in text
    assert PUBLISHED_SHA256 in text
    assert "Accessed:" in text
    assert "github.com/serverlessworkflow/specification/blob/v1.1.0/LICENSE" in text


def run_code(prefix, *argv):
    code = (
        "import sys, runpy; " + prefix + "; "
        f"sys.argv = {[str(SCRIPT), *map(str, argv)]!r}; "
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"
    )
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


@needs_deps
@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"- a\n- b\n",
        b"just a scalar\n",
        VALID.encode() + b"---\n" + VALID.encode(),
        VALID.encode("utf-16"),
        VALID.encode() + b"# caf\xe9\n",
    ],
    ids=["empty", "list", "scalar", "multi-doc", "utf16-bom", "latin1-byte"],
)
def test_ok_never_appears_for_a_non_flow_input(tmp_path, content):
    p = tmp_path / "flow.yaml"
    p.write_bytes(content)
    r = run(p)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "OK" not in r.stdout
    assert "Traceback" not in r.stderr


@needs_deps
@pytest.mark.parametrize(
    "content", [VALID.encode() + b"---\n" + VALID.encode(), VALID.encode("utf-16"), VALID.encode() + b"# caf\xe9\n"]
)
def test_unparseable_input_exits_2(tmp_path, content):
    p = tmp_path / "flow.yaml"
    p.write_bytes(content)
    assert run(p).returncode == 2


@needs_deps
def test_a_directory_exits_2(tmp_path):
    r = run(tmp_path)
    assert r.returncode == 2
    assert "OK" not in r.stdout


@needs_deps
def test_a_duplicate_mapping_key_exits_2(tmp_path):
    r = run(write(tmp_path, VALID.replace("  version: 0.1.0\n", "  version: 0.1.0\n  name: other\n")))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "duplicate" in r.stderr
    assert "OK" not in r.stdout


@needs_deps
@pytest.mark.parametrize("schema_text", ["", "{}\n", "type: 5\n"], ids=["empty", "empty-mapping", "invalid"])
def test_a_bad_schema_exits_2_and_never_passes(tmp_path, schema_text):
    schema = tmp_path / "schema.yaml"
    schema.write_text(schema_text)
    flow = tmp_path / "flow.yaml"
    flow.write_text(VALID)
    r = subprocess.run([sys.executable, str(SCRIPT), "--schema", str(schema), str(flow)], capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "OK" not in r.stdout


def test_a_jsonschema_without_draft_2020_12_exits_3(tmp_path):
    p = write(tmp_path, VALID)
    r = run_code(
        "import types; sys.modules['yaml'] = types.ModuleType('yaml'); "
        "sys.modules['jsonschema'] = types.ModuleType('jsonschema')",
        p,
    )
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Draft202012Validator" in r.stderr
    assert "Traceback" not in r.stderr
    assert "OK" not in r.stdout
