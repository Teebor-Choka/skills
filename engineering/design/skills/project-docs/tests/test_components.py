"""Tests for scripts/components.py: the component resolver and its needs-input halt (spec AT-1 to AT-4,
plus the lazy-tomllib half of AT-25)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import components  # noqa: E402  (path wired in conftest.py)
from docs_helpers import cargo_member, cargo_workspace, package_json, policy, write

SCRIPT = Path(components.__file__)


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                          capture_output=True, text=True, timeout=60)


def summary(repo: Path, **kw) -> list[tuple[str, str, tuple[str, ...]]]:
    return [(c.name, c.path, c.depends_on) for c in components.resolve(repo, **kw)]


# --- AT-1: Cargo --------------------------------------------------------------


def test_cargo_globbed_members_sorted_by_path_with_exclude(tmp_path):
    cargo_workspace(tmp_path, members='"crates/*", "tools/x"', exclude='"crates/skip"')
    # Names disagree with directory order on purpose: the sort key is the relpath.
    cargo_member(tmp_path, "zz-first", dir="m1")
    cargo_member(tmp_path, "aa-second", dir="m2", deps=("zz-first",))
    cargo_member(tmp_path, "skipped", dir="skip")
    write(tmp_path, "crates/not-a-crate/README.md", "no manifest\n")
    write(tmp_path, "tools/x/Cargo.toml", '[package]\nname = "tool-x"\n')
    assert summary(tmp_path) == [
        ("zz-first", "crates/m1", ()),
        ("aa-second", "crates/m2", ("zz-first",)),
        ("tool-x", "tools/x", ()),
    ]


def test_cargo_dev_and_build_dependencies_are_not_edges(tmp_path):
    cargo_workspace(tmp_path)
    cargo_member(tmp_path, "a")
    cargo_member(tmp_path, "b", dev=("a",), build=("a",))
    assert summary(tmp_path) == [("a", "crates/a", ()), ("b", "crates/b", ())]


def test_cargo_single_package_is_one_component(tmp_path):
    write(tmp_path, "Cargo.toml", '[package]\nname = "solo"\n')
    assert summary(tmp_path) == [("solo", ".", ())]


# --- AT-2: npm, uv, go --------------------------------------------------------


@pytest.mark.parametrize("workspaces", [["packages/*"], {"packages": ["packages/*"]}],
                         ids=["array", "object"])
def test_npm_workspaces(tmp_path, workspaces):
    package_json(tmp_path, "", "root", workspaces=workspaces)
    package_json(tmp_path, "packages/b", "b", dependencies={"a": "*", "left-pad": "1"})
    package_json(tmp_path, "packages/a", "a", devDependencies={"b": "*"})
    assert summary(tmp_path) == [("a", "packages/a", ()), ("b", "packages/b", ("a",))]


def test_uv_workspace_dev_group_is_not_an_edge(tmp_path):
    write(tmp_path, "pyproject.toml", '[tool.uv.workspace]\nmembers = ["libs/*"]\n')
    write(tmp_path, "libs/a/pyproject.toml", '[project]\nname = "a"\ndependencies = []\n')
    write(tmp_path, "libs/b/pyproject.toml",
          '[project]\nname = "b"\ndependencies = ["A>=1", "requests"]\n'
          '[dependency-groups]\ndev = ["pytest"]\n')
    write(tmp_path, "libs/c/pyproject.toml",
          '[project]\nname = "c"\n[dependency-groups]\ndev = ["a"]\n')
    assert summary(tmp_path) == [("a", "libs/a", ()), ("b", "libs/b", ("a",)), ("c", "libs/c", ())]


def test_uv_single_package(tmp_path):
    write(tmp_path, "pyproject.toml", '[project]\nname = "solo"\n')
    assert summary(tmp_path) == [("solo", ".", ())]


def test_go_work_modules_and_single_module(tmp_path):
    write(tmp_path, "go.work", "go 1.22\n\nuse (\n\t./b\n\t./a\n)\n")
    write(tmp_path, "a/go.mod", "module example.com/org/a\n\ngo 1.22\n")
    write(tmp_path, "b/go.mod",
          "module example.com/org/b\n\nrequire (\n\texample.com/org/a v0.0.0\n\tgolang.org/x/y v1.0.0\n)\n")
    assert summary(tmp_path) == [("a", "a", ()), ("b", "b", ("a",))]
    single = tmp_path / "single"
    write(single, "go.mod", "module example.com/org/solo\n")
    assert summary(single) == [("solo", ".", ())]


# --- AT-3: unsupported workspace halts ----------------------------------------


def test_pnpm_only_exits_3_with_needs_input_json(tmp_path):
    write(tmp_path, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    run = run_cli(str(tmp_path))
    assert run.returncode == 3
    out = json.loads(run.stdout)  # stdout is the JSON object and nothing else
    assert out["status"] == "needs-input"
    assert out["tool"] == "components.py"
    (missing,) = out["missing"]
    assert missing["field"] == "components"
    assert "pnpm-workspace.yaml" in missing["reason"]
    assert missing["supply"] == ["--components 'packages/*'", ".agents/policy docs.components.include"]


def test_halt_never_prompts_without_interactive(tmp_path):
    write(tmp_path, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    package_json(tmp_path, "packages/a", "a")
    run = run_cli(str(tmp_path), stdin="packages/*\n")
    assert run.returncode == 3 and "?" not in run.stdout


def test_interactive_turns_the_halt_into_a_question(tmp_path):
    write(tmp_path, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    package_json(tmp_path, "packages/a", "a")
    run = run_cli(str(tmp_path), "--interactive", stdin="packages/*\n")
    assert run.returncode == 0, run.stderr
    assert [c["name"] for c in json.loads(run.stdout)["components"]] == ["a"]


@pytest.mark.parametrize("marker", ["WORKSPACE", "MODULE.bazel", "settings.gradle", "settings.gradle.kts"])
def test_other_unparseable_workspaces_halt(tmp_path, marker):
    write(tmp_path, marker, "\n")
    with pytest.raises(components.NeedsInput) as exc:
        components.resolve(tmp_path)
    assert exc.value.missing[0]["field"] == "components"


def test_components_flag_replaces_the_halt(tmp_path):
    write(tmp_path, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    package_json(tmp_path, "packages/b", "b", dependencies={"a": "1"})
    package_json(tmp_path, "packages/a", "a")
    run = run_cli(str(tmp_path), "--components", "packages/*")
    assert run.returncode == 0, run.stderr
    got = [(c["name"], c["path"], c["depends-on"]) for c in json.loads(run.stdout)["components"]]
    assert got == [("a", "packages/a", []), ("b", "packages/b", ["a"])]


# --- AT-4: declared modules ---------------------------------------------------


def test_policy_include_declares_modules_named_by_directory(tmp_path):
    write(tmp_path, "Cargo.toml", '[package]\nname = "a"\n')
    for mod in ("net", "fs", "util"):
        write(tmp_path, f"crates/a/src/{mod}/mod.rs", "pub fn f() {}\n")
    write(tmp_path, "crates/a/src/lib.rs", "")
    policy(tmp_path, 'docs:\n  components:\n    include: ["crates/a/src/*/"]')
    assert summary(tmp_path) == [
        ("fs", "crates/a/src/fs", ()),
        ("net", "crates/a/src/net", ()),
        ("util", "crates/a/src/util", ()),
    ]


def test_policy_exclude_removes_members_and_edges(tmp_path):
    cargo_workspace(tmp_path)
    cargo_member(tmp_path, "a")
    cargo_member(tmp_path, "b", deps=("a",))
    policy(tmp_path, "docs:\n  components:\n    exclude:\n      a: test helper, no public API")
    assert summary(tmp_path) == [("b", "crates/b", ())]


def test_policy_reader_agrees_with_the_shared_loader(tmp_path):
    body = ('docs:\n  components:\n    include: ["crates/*/src/*/", pkgs/*]  # two globs\n'
            '    exclude:\n      "@scope/x": generated, see: gen.py')
    policy(tmp_path, body)
    loader_path = Path(__file__).resolve().parents[5] / "agents/ops/skills/policy"
    if not (loader_path / "policy_loader.py").is_file():
        pytest.skip("shared policy loader not in this checkout")
    sys.path.insert(0, str(loader_path))
    try:
        import policy_loader
        node = policy_loader._load_file(str(tmp_path / ".agents" / "policy.md"))["docs"]["components"]
    finally:
        sys.path.remove(str(loader_path))
    include, exclude = components.policy_options(tmp_path)
    assert include == node["include"]
    assert exclude == node["exclude"]


# --- failures -----------------------------------------------------------------


def test_tomllib_is_imported_only_for_toml_manifests(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "tomllib", None)  # as on Python 3.9 and 3.10
    package_json(tmp_path, "", "root", workspaces=["packages/*"])
    package_json(tmp_path, "packages/a", "a")
    assert summary(tmp_path) == [("a", "packages/a", ())]
    cargo = tmp_path / "cargo"
    write(cargo, "Cargo.toml", '[package]\nname = "x"\n')
    with pytest.raises(components.ManifestError, match=r"python 3\.11\+ required to parse .*Cargo\.toml"):
        components.resolve(cargo)


def test_broken_manifest_exits_2_naming_the_file(tmp_path):
    write(tmp_path, "Cargo.toml", "[workspace\nmembers = [")
    run = run_cli(str(tmp_path))
    assert run.returncode == 2
    assert "Cargo.toml" in run.stderr and run.stdout == ""


def test_duplicate_component_names_exit_2(tmp_path):
    cargo_workspace(tmp_path)
    cargo_member(tmp_path, "same", dir="one")
    cargo_member(tmp_path, "same", dir="two")
    run = run_cli(str(tmp_path))
    assert run.returncode == 2 and "same" in run.stderr


def test_missing_project_dir_exits_2(tmp_path):
    assert run_cli(str(tmp_path / "nope")).returncode == 2


def test_no_manifests_is_an_empty_set_not_a_guess(tmp_path):
    write(tmp_path, "src/a/main.txt", "x\n")
    assert summary(tmp_path) == []


def test_page_name_replaces_characters_outside_the_set():
    assert components.page_name("sandy-fsutil") == "sandy-fsutil"
    assert components.page_name("@scope/pkg_x") == "-scope-pkg-x"
