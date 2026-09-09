"""Regression tests for code-quality:measure against the fixtures in tests/fixtures/.

Wired into `nix flake check` (see flake.nix's `code-quality-tests` check and
nix/code-quality-tools.nix) on aarch64-darwin and x86_64-linux, where every
required tool (cargo-crap, cargo-iceberg4rust, rust-code-analysis-cli,
crap4py, complexipy, pyscn, jscpd, jq, git) is provisioned hermetically —
either straight from nixpkgs or from a pinned fetch for tools nixpkgs
doesn't package. Can also be run directly with those tools on PATH some
other way: `pytest tests/`.

Each required tool's presence is checked explicitly and the whole module is
skipped (not failed) if any are missing, per the skill's own philosophy in
SKILL.md: "don't assume any particular way they got there... missing -> say
what's missing." Fixture git history is synthesized at test time rather than
committed (a tracked `.git` directory inside this repo would be interpreted
as a submodule reference, not real history) — the exact commit counts below
are what the assertions are keyed to.

Assertions are pinned to these specific fixtures and the tool versions
installed when this was written. A tool upgrade that changes its scoring
algorithm (not just this test's tool versions drifting) is a real reason
for a value here to change — re-verify by hand before updating an
assertion, don't just make the failure go away.
"""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

RUST_TOOLS = [
    "cargo",
    "cargo-crap",
    "cargo-iceberg4rust",
    "cargo-llvm-cov",
    "rust-code-analysis-cli",
    "jscpd",
    "jq",
    "git",
]
PYTHON_TOOLS = ["python3", "pytest", "crap4py", "complexipy", "pyscn", "jscpd", "jq", "git"]

missing_rust_tools = [t for t in RUST_TOOLS if shutil.which(t) is None]
missing_python_tools = [t for t in PYTHON_TOOLS if shutil.which(t) is None]

pytestmark = pytest.mark.skipif(
    missing_rust_tools or missing_python_tools,
    reason=(
        "missing required tools for a real run: "
        f"rust={missing_rust_tools or 'ok'}, python={missing_python_tools or 'ok'} "
        "-- see references/rust.md and references/python.md for how to install them"
    ),
)


def _make_writable(root: Path) -> None:
    """shutil.copytree preserves the source's permission bits, including on
    the directories themselves — when the source is a Nix store path (this
    module's own fixtures/, read-only by design), the copy comes out
    read-only too, and `git init` can't create .git/ inside it. Found by
    running this suite under `nix build` specifically, since every other
    way of exercising these fixtures this project used copied them from a
    normal writable filesystem instead, where copytree's permission
    preservation was a no-op."""
    for path in [root, *root.rglob("*")]:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)


def _git_commit(repo: Path, message: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t.com",
    }
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=repo, check=True, capture_output=True, env=env
    )


@pytest.fixture(scope="module")
def rust_manifest(tmp_path_factory) -> Path:
    """A real git working copy of the Rust fixture with 3 commits touching
    src/lib.rs (1 initial + 2 churn) — rust:hotspots' expected touches=3 is
    keyed to this exact count."""
    project_dir = tmp_path_factory.mktemp("rust-sample")
    shutil.copytree(FIXTURES_DIR / "rust-sample", project_dir, dirs_exist_ok=True)
    _make_writable(project_dir)
    subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True)
    _git_commit(project_dir, "initial")
    for i in range(2):
        with (project_dir / "src" / "lib.rs").open("a") as f:
            f.write(f"// churn {i + 1}\n")
        _git_commit(project_dir, f"churn {i + 1}")
    return project_dir / "Cargo.toml"


@pytest.fixture(scope="module")
def python_manifest(tmp_path_factory) -> Path:
    """A real git working copy of the Python fixture with 2 commits touching
    pkg/core.py (1 initial + 1 churn) — python:hotspots' expected
    core.py touches=2 is keyed to this exact count."""
    project_dir = tmp_path_factory.mktemp("python-sample")
    shutil.copytree(FIXTURES_DIR / "python-sample", project_dir, dirs_exist_ok=True)
    _make_writable(project_dir)
    subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True)
    _git_commit(project_dir, "initial")
    with (project_dir / "pkg" / "core.py").open("a") as f:
        f.write("# churn\n")
    _git_commit(project_dir, "churn")
    return project_dir / "pyproject.toml"


@pytest.fixture(scope="module")
def measure(rust_manifest, python_manifest) -> dict:
    """One real run.sh invocation covering both fixtures, shared by every
    test below — run.sh's own parallel fan-out already covers the
    "expensive to run" concern, no need to re-run it per assertion."""
    result = subprocess.run(
        [str(SKILL_DIR / "assets" / "run.sh"), str(rust_manifest), str(python_manifest)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"run.sh failed: {result.stderr}"
    return json.loads(result.stdout)


def test_stdout_is_pure_json_nothing_else_mixed_in(measure):
    assert set(measure.keys()) == {"discovery", "results"}


def test_discovery_found_every_tool(measure):
    assert measure["discovery"]["missing"] == []
    assert set(measure["discovery"]["available"]) == {
        "rust:filerisk", "rust:crap", "rust:cognitive", "rust:hotspots", "rust:duplication",
        "python:crap", "python:cognitive", "python:hotspots", "python:duplication", "python:iad",
    }


def test_rust_filerisk_finds_nothing_in_a_small_file(measure):
    filerisk = measure["results"]["rust:filerisk"]
    assert filerisk["rows"] == []
    assert filerisk["summary"]["scored_files"] == 0


def test_rust_crap(measure):
    rows = {r["function"]: r for r in measure["results"]["rust:crap"]["rows"]}
    assert rows["classify2"]["cc"] == 4
    assert rows["classify2"]["coverage"] == 0.0
    assert rows["classify2"]["crap"] == pytest.approx(20.0)
    assert rows["classify2"]["flagged"] is False  # under the 30 threshold, just untested

    assert rows["classify"]["cc"] == 4
    assert rows["classify"]["coverage"] == pytest.approx(66.66666666666666)
    assert rows["classify"]["crap"] == pytest.approx(4.5925925925925934)

    assert rows["trivial"]["crap"] == pytest.approx(2.0)
    assert measure["results"]["rust:crap"]["summary"]["flagged"] == 0


def test_rust_cognitive(measure):
    rows = {r["function"]: r["complexity"] for r in measure["results"]["rust:cognitive"]["rows"]}
    assert rows["classify"] == pytest.approx(4.0)
    assert rows["classify2"] == pytest.approx(4.0)
    assert rows["trivial"] == pytest.approx(0.0)


def test_rust_hotspots(measure):
    rows = measure["results"]["rust:hotspots"]["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["file"] == "src/lib.rs"
    assert row["touches"] == 3  # 1 initial + 2 churn commits, see rust_manifest fixture
    assert row["complexity"] == pytest.approx(8.0)  # classify(4) + classify2(4) + trivial(0)
    assert row["hotspot"] == pytest.approx(24.0)  # 3 * 8.0


def test_rust_duplication_finds_none(measure):
    assert measure["results"]["rust:duplication"]["summary"]["clones"] == 0


def test_python_crap(measure):
    rows = {r["function"]: r for r in measure["results"]["python:crap"]["rows"]}
    assert rows["classify2"]["crap"] == pytest.approx(20.0)
    assert rows["classify2"]["file"] == "pkg/helpers.py"
    assert rows["classify2"]["line"] is None  # crap4py has no line-number column at all

    assert rows["classify"]["crap"] == pytest.approx(6.0)
    assert rows["classify"]["coverage"] == pytest.approx(50.0)
    assert measure["results"]["python:crap"]["summary"]["flagged"] == 0


def test_python_cognitive(measure):
    rows = {r["function"]: r["complexity"] for r in measure["results"]["python:cognitive"]["rows"]}
    assert rows["classify"] == 4
    assert rows["classify2"] == 4
    assert rows["Shape::area"] == 0


def test_python_hotspots(measure):
    rows = {r["file"]: r for r in measure["results"]["python:hotspots"]["rows"]}
    assert rows["pkg/core.py"]["touches"] == 2  # 1 initial + 1 churn, see python_manifest fixture
    assert rows["pkg/core.py"]["complexity"] == 4
    assert rows["pkg/core.py"]["hotspot"] == pytest.approx(8.0)
    assert rows["pkg/helpers.py"]["touches"] == 1


def test_python_duplication_finds_none(measure):
    assert measure["results"]["python:duplication"]["summary"]["clones"] == 0


def test_python_iad(measure):
    rows = {r["module"]: r for r in measure["results"]["python:iad"]["rows"]}
    # pkg.core: depended on by pkg.helpers (Ca=1), depends on nothing (Ce=0),
    # its one class is an abc.ABC subclass (A=1) -- sits exactly on the main
    # sequence (D=0), as a foundational module should.
    assert rows["pkg.core"]["ca"] == 1
    assert rows["pkg.core"]["ce"] == 0
    assert rows["pkg.core"]["instability"] == 0
    assert rows["pkg.core"]["abstractness"] == 1
    assert rows["pkg.core"]["distance"] == 0

    # pkg.helpers: depends on pkg.core (Ce=1), nothing depends on it (Ca=0),
    # no classes of its own (A=0) -- unstable and concrete, correct for glue
    # code, also D=0.
    assert rows["pkg.helpers"]["ca"] == 0
    assert rows["pkg.helpers"]["ce"] == 1
    assert rows["pkg.helpers"]["instability"] == 1
    assert rows["pkg.helpers"]["abstractness"] == 0
