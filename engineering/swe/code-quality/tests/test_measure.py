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
    "cargo-anatomy",
    "cargo-mutants",
    "cargo-machete",
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
        timeout=300,  # several build-based metrics (crap, deadcode, api, cargo-modules) run here
    )
    assert result.returncode == 0, f"run.sh failed: {result.stderr}"
    return json.loads(result.stdout)


def test_stdout_is_pure_json_nothing_else_mixed_in(measure):
    assert set(measure.keys()) == {"discovery", "results"}


def test_discovery_found_every_tool(measure):
    assert measure["discovery"]["missing"] == []
    assert set(measure["discovery"]["available"]) == {
        "rust:filerisk", "rust:crap", "rust:cognitive", "rust:hotspots", "rust:duplication",
        "rust:iad", "rust:mi", "rust:halstead", "rust:loc", "rust:nom",
        "rust:deadcode", "rust:deps", "rust:unsafe", "rust:api", "rust:orphans", "rust:fanio",
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


def test_rust_iad_single_crate(measure):
    # The rust-sample fixture is one leaf crate with no other workspace member
    # to couple to, so Ca=Ce=0. It also has zero type definitions (only
    # functions), the N=0 case: cargo-anatomy yields a=0, i=0, d=|0+0-1|/sqrt2
    # rather than a NaN from the 0/0 -- confirming the metric degrades cleanly
    # in the pipeline. The real coupling relationship is exercised by
    # test_rust_iad_workspace below.
    rows = {r["crate"]: r for r in measure["results"]["rust:iad"]["rows"]}
    assert set(rows) == {"sample"}
    assert rows["sample"]["ca"] == 0
    assert rows["sample"]["ce"] == 0
    assert rows["sample"]["abstractness"] == pytest.approx(0.0)
    assert rows["sample"]["instability"] == pytest.approx(0.0)
    assert rows["sample"]["distance"] == pytest.approx(0.7071067811865475)
    assert measure["results"]["rust:iad"]["summary"]["crates"] == 1


# The rust:mi/halstead/loc/nom values below are keyed to the rust_manifest
# fixture *after* its 2 churn commits, each appending one comment line to
# src/lib.rs (see the rust_manifest fixture): halstead and nom are
# comment-invariant (comments are not tokens or functions), while mi and loc
# shift with the 2 added comment lines (cloc 0 -> 2).
def test_rust_mi(measure):
    rows = measure["results"]["rust:mi"]["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["file"] == "src/lib.rs"
    assert row["mi_visual_studio"] == pytest.approx(45.29717569244738)
    assert row["mi_original"] == pytest.approx(77.45817043408502)
    assert row["mi_sei"] == pytest.approx(54.35123432572237)


def test_rust_halstead(measure):
    rows = measure["results"]["rust:halstead"]["rows"]
    row = rows[0]
    assert row["file"] == "src/lib.rs"
    assert row["volume"] == pytest.approx(440.92347162443184)
    assert row["effort"] == pytest.approx(5891.22749587088)
    assert row["vocabulary"] == 31
    assert row["length"] == 89


def test_rust_loc(measure):
    rows = {r["file"]: r for r in measure["results"]["rust:loc"]["rows"]}
    row = rows["src/lib.rs"]
    assert row["sloc"] == 39  # 37 in the pristine fixture + 2 churn comment lines
    assert row["ploc"] == 33
    assert row["lloc"] == 3
    assert row["cloc"] == 2  # the 2 churn comment lines
    assert row["blank"] == 4


def test_rust_nom(measure):
    rows = {r["file"]: r for r in measure["results"]["rust:nom"]["rows"]}
    row = rows["src/lib.rs"]
    assert row["functions"] == 4  # classify, trivial, classify2, and the one test fn
    assert row["closures"] == 0
    assert row["total"] == 4


def test_rust_structural_metrics_clean_on_sample(measure):
    # The rust-sample fixture has no dead code (its unused fns are pub), no
    # dependencies, and no unsafe — so the structural metrics run in the default
    # sweep and find nothing, the "no findings" baseline.
    assert measure["results"]["rust:deadcode"]["rows"] == []
    assert measure["results"]["rust:deps"]["rows"] == []
    assert measure["results"]["rust:unsafe"]["rows"] == []


def test_rust_modulegraph_metrics_on_sample(measure):
    # rust-sample is a single-file crate: no orphan files, a public API of its
    # crate root plus a few pub fns, and one module (so no cross-module
    # coupling). Exact API/fanio values are pinned on the modules fixture below.
    assert measure["results"]["rust:orphans"]["rows"] == []
    assert measure["results"]["rust:api"]["summary"]["public_items"] >= 3
    fanio_modules = {r["module"] for r in measure["results"]["rust:fanio"]["rows"]}
    assert "sample" in fanio_modules


def test_mutation_is_excluded_from_the_default_sweep(measure):
    # Mutation testing is far heavier than the other metrics, so run.sh leaves
    # it out of `measure` unless CODE_QUALITY_ENABLE_MUTATION is set.
    assert "rust:mutation" not in measure["discovery"]["available"]
    assert "rust:mutation" not in measure["results"]


def test_rust_mutation(rust_manifest):
    """rust:mutation via cargo-mutants, run directly (it's opt-in in the default
    sweep). The fixture's single test exercises only classify(), so mutants in
    trivial()/classify2() survive: 21 mutants, 6 caught, 15 missed, 0 unviable,
    score 6/21. Keyed to the pinned cargo-mutants version (a version change to
    its mutation operators is a real reason for these counts to move)."""
    mutation = SKILL_DIR / "assets" / "lang" / "rust" / "mutation.sh"
    result = subprocess.run(
        [str(mutation), str(rust_manifest)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"mutation.sh failed: {result.stderr}"
    payload = json.loads(result.stdout)
    s = payload["summary"]
    assert s["total_mutants"] == 21
    assert s["caught"] == 6
    assert s["missed"] == 15
    assert s["unviable"] == 0
    assert s["score"] == pytest.approx(6 / 21)
    assert len(payload["rows"]) == 15  # one row per surviving (missed) mutant
    assert all(r["file"] == "src/lib.rs" for r in payload["rows"])


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


@pytest.fixture(scope="module")
def rust_workspace_manifest(tmp_path_factory) -> Path:
    """A writable copy of the two-crate rust-iad-sample workspace. No git
    history is synthesized (unlike the single-crate fixture): iad is a pure
    static-analysis metric with no churn component, so it needs none."""
    project_dir = tmp_path_factory.mktemp("rust-iad-sample")
    shutil.copytree(FIXTURES_DIR / "rust-iad-sample", project_dir, dirs_exist_ok=True)
    _make_writable(project_dir)
    return project_dir / "Cargo.toml"


def test_rust_iad_workspace(rust_workspace_manifest):
    """rust:iad on a real two-crate workspace, exercising the Ca/Ce coupling
    the single-crate fixture can't. `core_lib` (a Shape trait + a Circle
    struct) is depended on by `app` (Ca=1) and depends on nothing (Ce=0) --
    stable and half-abstract (A=0.5). `app` (one struct holding a Circle)
    depends on core_lib (Ce=1) with nothing depending on it (Ca=0) -- fully
    unstable and concrete. iad.sh is invoked directly rather than via the
    combined run because run.sh takes one Cargo.toml per language and the
    other Rust metrics want a package manifest, not a workspace root."""
    iad = SKILL_DIR / "assets" / "lang" / "rust" / "iad.sh"
    result = subprocess.run(
        [str(iad), str(rust_workspace_manifest)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"iad.sh failed: {result.stderr}"
    payload = json.loads(result.stdout)
    rows = {r["crate"]: r for r in payload["rows"]}
    assert set(rows) == {"core_lib", "app"}

    assert rows["core_lib"]["ca"] == 1
    assert rows["core_lib"]["ce"] == 0
    assert rows["core_lib"]["instability"] == pytest.approx(0.0)
    assert rows["core_lib"]["abstractness"] == pytest.approx(0.5)
    assert rows["core_lib"]["distance"] == pytest.approx(0.35355339059327373)

    assert rows["app"]["ca"] == 0
    assert rows["app"]["ce"] == 1
    assert rows["app"]["instability"] == pytest.approx(1.0)
    assert rows["app"]["abstractness"] == pytest.approx(0.0)
    assert rows["app"]["distance"] == pytest.approx(0.0)

    assert payload["summary"]["crates"] == 2


def test_rust_iad_external_scope_no_match_falls_back(rust_workspace_manifest):
    """CODE_QUALITY_IAD_EXTERNAL_SCOPE widens the graph to matching external
    crates. A scope matching nothing is a hard error in cargo-anatomy ("no
    external crates matched"), which would otherwise abort a run over a project
    that legitimately has no matching external dependency -- iad.sh degrades to
    the members-only view (with a stderr note) for that case. Actual external
    inclusion needs registry dependencies and is validated on a real
    multi-workspace repo, not in this offline, dependency-free fixture."""
    iad = SKILL_DIR / "assets" / "lang" / "rust" / "iad.sh"
    result = subprocess.run(
        [str(iad), str(rust_workspace_manifest)],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "CODE_QUALITY_IAD_EXTERNAL_SCOPE": "pkg-prefix:zzz-no-such-crate"},
    )
    assert result.returncode == 0, f"iad.sh failed: {result.stderr}"
    assert "falling back" in result.stderr
    payload = json.loads(result.stdout)
    assert {r["crate"] for r in payload["rows"]} == {"core_lib", "app"}


@pytest.fixture(scope="module")
def structural_manifest(tmp_path_factory) -> Path:
    """A writable copy of rust-structural-sample (one unsafe fn + one dead
    private fn, no dependencies). Writable because rust:deadcode runs
    `cargo check`, which needs to write target/."""
    project_dir = tmp_path_factory.mktemp("rust-structural-sample")
    shutil.copytree(FIXTURES_DIR / "rust-structural-sample", project_dir, dirs_exist_ok=True)
    _make_writable(project_dir)
    return project_dir / "Cargo.toml"


@pytest.fixture(scope="module")
def unuseddep_manifest(tmp_path_factory) -> Path:
    """A writable copy of rust-unuseddep-sample (declares a `helper` path
    dependency it never uses)."""
    project_dir = tmp_path_factory.mktemp("rust-unuseddep-sample")
    shutil.copytree(FIXTURES_DIR / "rust-unuseddep-sample", project_dir, dirs_exist_ok=True)
    _make_writable(project_dir)
    return project_dir / "Cargo.toml"


def _run_metric(name: str, manifest: Path) -> dict:
    script = SKILL_DIR / "assets" / "lang" / "rust" / f"{name}.sh"
    result = subprocess.run(
        [str(script), str(manifest)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"{name}.sh failed: {result.stderr}"
    return json.loads(result.stdout)


def test_rust_deadcode(structural_manifest):
    payload = _run_metric("deadcode", structural_manifest)
    rows = payload["rows"]
    assert len(rows) == 1
    assert rows[0]["lint"] == "dead_code"
    assert rows[0]["file"] == "src/lib.rs"
    assert "dead_helper" in rows[0]["message"]
    assert payload["summary"]["findings"] == 1


def test_rust_unsafe(structural_manifest):
    payload = _run_metric("unsafe", structural_manifest)
    rows = {r["file"]: r for r in payload["rows"]}
    # `pub unsafe fn` + the `unsafe { }` block = 2 keyword occurrences.
    assert rows["src/lib.rs"]["unsafe"] == 2
    assert payload["summary"] == {"files_with_unsafe": 1, "total_unsafe": 2}


def test_rust_deps(unuseddep_manifest):
    payload = _run_metric("deps", unuseddep_manifest)
    rows = payload["rows"]
    assert rows == [{"crate": "unuseddep", "dependency": "helper"}]
    assert payload["summary"]["unused"] == 1


@pytest.fixture(scope="module")
def modules_manifest(tmp_path_factory) -> Path:
    """A writable copy of rust-modules-sample: a public API, two submodules with
    cross-module `uses` edges, and an unlinked orphan file."""
    project_dir = tmp_path_factory.mktemp("rust-modules-sample")
    shutil.copytree(FIXTURES_DIR / "rust-modules-sample", project_dir, dirs_exist_ok=True)
    _make_writable(project_dir)
    return project_dir / "Cargo.toml"


def test_rust_api(modules_manifest):
    payload = _run_metric("api", modules_manifest)
    items = [r["item"] for r in payload["rows"]]
    # crate root + widgets mod + wrap fn + Gadget struct + its id field + make_gadget.
    # Match items by substring, not exact signature — cargo-public-api's rendering
    # of a signature shifts between versions (0.51 vs 0.52), the count does not.
    assert payload["summary"]["public_items"] == 6
    assert any("struct apisample::Gadget" in i for i in items)
    assert any("make_gadget" in i for i in items)
    assert any("widgets::wrap" in i for i in items)
    assert not any(i.startswith("impl ") for i in items)  # auto-trait impls filtered out


def test_rust_orphans(modules_manifest):
    payload = _run_metric("orphans", modules_manifest)
    assert payload["rows"] == [{"module": "orphan", "file": "src/orphan.rs"}]
    assert payload["summary"]["orphans"] == 1


def test_rust_fanio(modules_manifest):
    payload = _run_metric("fanio", modules_manifest)
    rows = {r["module"]: r for r in payload["rows"]}
    assert payload["summary"]["modules"] == 3
    # widgets and make_gadget both use Gadget (owned by the crate root), so the
    # crate root has fan_in=1 and widgets has fan_out=1; internal is isolated.
    assert rows["apisample"]["fan_in"] == 1
    assert rows["apisample"]["fan_out"] == 0
    assert rows["apisample::widgets"]["fan_out"] == 1
    assert rows["apisample::internal"] == {
        "module": "apisample::internal",
        "fan_in": 0,
        "fan_out": 0,
    }
