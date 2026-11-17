"""Tests for scripts/install_hook.sh against real temporary git repos.

Each test installs the hook into a throwaway repo (a copy of the conformant
fixture) and drives real `git commit` calls, so the hook is judged by what git
does with it: block or allow. Standard library plus pytest.
"""

import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE = TESTS_DIR / "fixtures" / "conformant"
SCRIPTS = TESTS_DIR.parent / "scripts"
MARKER = "# >>> project-docs validate_docs hook >>>"

ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def run(*cmd, cwd=None, check=False):
    return subprocess.run(
        [str(c) for c in cmd], cwd=cwd, env=ENV, capture_output=True, text=True,
        timeout=60, check=check,
    )


def git(cwd, *args, check=True):
    return run("git", *args, cwd=cwd, check=check)


def make_scripts(base: Path, name: str) -> Path:
    d = base / name
    d.mkdir()
    for f in ("validate_docs.py", "install_hook.sh"):
        shutil.copy(SCRIPTS / f, d / f)
    return d


def make_repo(base: Path, name: str) -> Path:
    r = base / name
    shutil.copytree(FIXTURE, r)
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    return r


WEIRD = " $x `bt` 'q' \"d\""


@pytest.fixture
def scripts(tmp_path) -> Path:
    return make_scripts(tmp_path, "scripts")


@pytest.fixture
def repo(tmp_path) -> Path:
    return make_repo(tmp_path, "repo")


@pytest.fixture
def weird_scripts(tmp_path) -> Path:
    return make_scripts(tmp_path, "sc ripts" + WEIRD)


@pytest.fixture
def weird_repo(tmp_path) -> Path:
    return make_repo(tmp_path, "my repo" + WEIRD)


def install(scripts: Path, target: Path) -> subprocess.CompletedProcess:
    return run("sh", scripts / "install_hook.sh", target)


def break_doc(root: Path) -> None:
    (root / "docs" / "overview.md").write_text("no frontmatter at all\n")


def commit_new_file(root: Path, name: str) -> subprocess.CompletedProcess:
    (root / name).write_text("x\n")
    git(root, "add", name)
    return git(root, "commit", "-q", "-m", name, check=False)


def test_hook_survives_paths_with_shell_metacharacters(weird_scripts, weird_repo):
    scripts, repo = weird_scripts, weird_repo
    assert install(scripts, repo).returncode == 0
    assert commit_new_file(repo, "ok.txt").returncode == 0
    broken = repo / "docs" / "overview.md"
    broken.write_text("no frontmatter\n")
    git(repo, "add", "docs/overview.md")
    result = git(repo, "commit", "-q", "-m", "bad", check=False)
    assert result.returncode != 0
    assert "frontmatter" in result.stdout + result.stderr


def test_printed_stanza_quotes_the_validator_path(weird_scripts, weird_repo):
    scripts, repo = weird_scripts, weird_repo
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n")
    out = install(scripts, repo).stdout
    entry = next(l for l in out.splitlines() if l.strip().startswith("entry:"))
    value = entry.split("entry:", 1)[1].strip()
    assert value.startswith("'") and value.endswith("'")  # YAML single-quoted
    # pre-commit shlex-splits the entry: it must round-trip to the real path
    argv = shlex.split(value[1:-1].replace("''", "'"))
    assert argv == ["python3", str(scripts / "validate_docs.py")]


def test_new_hook_uses_a_portable_shebang(scripts, repo):
    # The Nix build sandbox has /bin/sh but no /usr/bin/env, so an env shebang
    # makes git fail to exec the hook there.
    install(scripts, repo)
    hook = (repo / ".git" / "hooks" / "pre-commit").read_text()
    assert hook.splitlines()[0] == "#!/bin/sh"


def test_rerun_does_not_duplicate_the_block(scripts, repo):
    install(scripts, repo)
    again = install(scripts, repo)
    assert again.returncode == 0
    hook = (repo / ".git" / "hooks" / "pre-commit").read_text()
    assert hook.count(MARKER) == 1


def test_symlinked_hook_is_left_alone(scripts, repo, tmp_path):
    target = tmp_path / "shared-hook.sh"
    target.write_text("#!/bin/sh\nexit 0\n")
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").symlink_to(target)
    result = install(scripts, repo)
    assert result.returncode == 0
    assert (hooks / "pre-commit").is_symlink()
    assert target.read_text() == "#!/bin/sh\nexit 0\n"
    assert MARKER in result.stdout


def test_shared_hooks_path_outside_the_repo_is_refused(scripts, repo, tmp_path):
    shared = tmp_path / "shared-hooks"
    shared.mkdir()
    git(repo, "config", "core.hooksPath", str(shared))
    result = install(scripts, repo)
    assert result.returncode == 0
    assert list(shared.iterdir()) == []
    assert MARKER in result.stdout


def test_hooks_path_inside_the_work_tree_is_used(scripts, repo):
    git(repo, "config", "core.hooksPath", ".githooks")
    assert install(scripts, repo).returncode == 0
    assert (repo / ".githooks" / "pre-commit").is_file()


def test_hook_blocks_a_broken_staged_doc_in_a_linked_worktree(scripts, repo, tmp_path):
    install(scripts, repo)
    wt = tmp_path / "linked wt"
    git(repo, "worktree", "add", "-q", str(wt), "-b", "feature")
    break_doc(wt)
    git(wt, "add", "docs/overview.md")
    result = git(wt, "commit", "-q", "-m", "bad", check=False)
    assert result.returncode != 0
    assert "frontmatter" in result.stdout + result.stderr


def test_hook_validates_staged_content_not_the_working_tree(scripts, repo):
    install(scripts, repo)
    break_doc(repo)  # unstaged breakage must not block a clean staged commit
    (repo / "notes.txt").write_text("x\n")
    git(repo, "add", "notes.txt")
    result = git(repo, "commit", "-q", "-m", "notes", check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hook_fails_clearly_when_the_validator_is_gone(scripts, repo):
    install(scripts, repo)
    (scripts / "validate_docs.py").unlink()
    result = commit_new_file(repo, "a.txt")
    assert result.returncode != 0
    out = result.stdout + result.stderr
    assert "validate_docs.py" in out and "install_hook.sh" in out


def make_subproject_repo(base: Path) -> Path:
    r = base / "mono"
    shutil.copytree(FIXTURE, r / "proj")
    (r / "other.txt").write_text("o\n")
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    return r


def test_subdir_target_does_not_block_an_unrelated_commit(scripts, tmp_path):
    mono = make_subproject_repo(tmp_path)
    (mono / "fresh").mkdir()  # exists on disk, nothing under it in the index
    assert install(scripts, mono / "fresh").returncode == 0
    (mono / "unrelated.txt").write_text("x\n")
    git(mono, "add", "unrelated.txt")
    result = git(mono, "commit", "-q", "-m", "u", check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_subdir_target_still_blocks_a_broken_staged_doc(scripts, tmp_path):
    mono = make_subproject_repo(tmp_path)
    install(scripts, mono / "proj")
    (mono / "proj" / "docs" / "overview.md").write_text("no frontmatter\n")
    git(mono, "add", "proj/docs/overview.md")
    assert git(mono, "commit", "-q", "-m", "b", check=False).returncode != 0


OLD_BLOCK = """#!/usr/bin/env sh
set -eu

# >>> project-docs validate_docs hook >>>
python3 "{v}" "{t}" || exit $?
# <<< project-docs validate_docs hook <<<
echo after-block
"""


def test_reinstall_upgrades_an_old_block_and_is_then_stable(scripts, repo):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(OLD_BLOCK.format(v=scripts / "validate_docs.py", t=repo))
    hook.chmod(0o755)
    assert install(scripts, repo).returncode == 0
    upgraded = hook.read_text()
    assert "checkout-index" in upgraded
    assert upgraded.count(MARKER) == 1 and "echo after-block" in upgraded
    assert install(scripts, repo).returncode == 0
    assert hook.read_text() == upgraded


def test_hook_exports_only_docs_and_agents_md(scripts, repo):
    install(scripts, repo)
    hook = (repo / ".git" / "hooks" / "pre-commit").read_text()
    assert "checkout-index -a" not in hook


def test_hook_removes_its_temp_dir_on_sigterm(scripts, repo, tmp_path):
    install(scripts, repo)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen = tmp_path / "seen"
    fake = bin_dir / "python3"
    fake.write_text(f'#!/bin/sh\nprintf %s "$2" > "{seen}"\nsleep 30\n')
    fake.chmod(0o755)
    proc = subprocess.Popen(
        [str(repo / ".git" / "hooks" / "pre-commit")], cwd=repo, start_new_session=True,
        env={**ENV, "PATH": f"{bin_dir}{os.pathsep}{ENV['PATH']}"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        if seen.exists() and seen.read_text():
            break
        time.sleep(0.1)
    exported = Path(seen.read_text().rstrip("/"))
    tmp_root = exported.parent
    assert tmp_root.exists()
    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(timeout=20)
    for _ in range(50):  # the subshell may finish cleanup just after its parent dies
        if not tmp_root.exists():
            break
        time.sleep(0.1)
    assert not tmp_root.exists()
